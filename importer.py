"""Read-only episode import; self-contained editable documents with stable source references."""
from pathlib import Path
import base64,copy,hashlib,json,sys,uuid,threading
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent.parent
EDITOR=ROOT/'editor'
CACHE=EDITOR/'cache'
SCHEMA='projectWT.editor/1'
LOCK=threading.Lock()
def now():return datetime.now(timezone.utc).isoformat()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def episode_path(ep):
    if len(ep)!=4 or ep[:2]!='EP' or not ep[2:].isdigit():raise ValueError('Invalid episode')
    p=(ROOT/'episodes'/ep).resolve()
    if not p.is_relative_to((ROOT/'episodes').resolve()):raise ValueError('Outside episodes')
    return p
def load_manifest(ep):
    p=episode_path(ep)/(ep+'_manifest.json')
    return p,json.loads(p.read_text(encoding='utf-8-sig'))
def catalog():
    result=[]
    for folder in sorted((ROOT/'episodes').glob('EP[0-9][0-9]')):
        ep=folder.name
        try:
            _,m=load_manifest(ep)
            result.append({'id':ep,'title':m.get('episode_title') or ep,'cutCount':len(m.get('cuts',[])),'available':(folder/(ep+'_reader.html')).is_file(),'bakedText':ep=='EP01'})
        except (OSError,ValueError):continue
    return {'episodes':result}
EXTRACT=r"""(async()=>{
await document.fonts.ready;
for(const im of document.querySelectorAll('img')){im.loading='eager';}
await Promise.all(Array.from(document.querySelectorAll('img')).map(im=>im.decode().catch(()=>{})));
const reader=document.querySelector('.reader')||document.querySelector('main'),rw=reader.getBoundingClientRect().width,k=1080/rw;
const rel=(r,s)=>({x:(r.left-s.left)*k,y:(r.top-s.top)*k,w:r.width*k,h:r.height*k});
let panels=[];
for(const s of document.querySelectorAll('.scene[data-cut]')){
 const sr=s.getBoundingClientRect(),layers=[];
 let n=0;
 for(const el of s.querySelectorAll('img.art,svg.art,.letter,.label,.memory-label,.intro')){
   const css=getComputedStyle(el),r=el.getBoundingClientRect();
   if(css.display==='none'||css.visibility==='hidden'||r.width<3||r.height<3||css.clipPath==='inset(50%)')continue;
   const box=rel(r,sr),id=s.dataset.cut+'-L'+(++n),tag=el.tagName.toLowerCase();
   if(tag==='img'||tag==='svg'){
     let src,width,height,path;
     if(tag==='svg'){
       const v=el.viewBox.baseVal,use=el.querySelector('use'),ref=use&&document.querySelector(use.getAttribute('href')),i=new Image();
       if(!ref)continue;i.src=ref.getAttribute('href');await i.decode();
       const cv=document.createElement('canvas');cv.width=Math.ceil(v.width);cv.height=Math.ceil(v.height);
       cv.getContext('2d').drawImage(i,v.x,v.y,v.width,v.height,0,0,cv.width,cv.height);
       src=cv.toDataURL('image/png');width=cv.width;height=cv.height;path=ref.getAttribute('href');
     }else{const cv=document.createElement('canvas');cv.width=el.naturalWidth;cv.height=el.naturalHeight;cv.getContext('2d').drawImage(el,0,0);src=cv.toDataURL('image/webp',.98);width=cv.width;height=cv.height;path=el.getAttribute('src');}
     layers.push({id,type:'image',...box,src,width,height,path,rotation:0,opacity:parseFloat(css.opacity)||1,locked:false});
   }else{
     const speech=el.classList.contains('speech'),thought=el.classList.contains('thought');
     layers.push({id,type:speech?'balloon':'text',...box,text:el.innerText,fontSize:parseFloat(css.fontSize)*k,lineHeight:parseFloat(css.lineHeight)*k,rotation:0,opacity:1,color:css.color,fill:speech?'#ffffff':'transparent',stroke:speech?'#29251e':'transparent',strokeWidth:speech?1.5*k:0,align:css.textAlign,speaker:el.dataset.speaker||'',shape:speech?'ellipse':thought?'thought':'box',tail:speech?{x:.38,y:1+20/Math.max(box.h,1)}:null,locked:false});
   }
 }
 panels.push({id:s.dataset.cut,originCutId:s.dataset.cut,title:s.getAttribute('aria-label')||s.dataset.cut,width:1080,height:Math.max(sr.height*k,80),background:getComputedStyle(s).backgroundColor==='rgba(0, 0, 0, 0)'?'#ffffff':getComputedStyle(s).backgroundColor,gapAfter:parseFloat(getComputedStyle(s).marginBottom)*k,notes:'',redraw:false,layers});
 // x must be relative to complete reader-width panel, not narrow source scene.
 const offset=(sr.left-reader.getBoundingClientRect().left)*k;
 for(const l of layers)l.x+=offset;
}
return {title:document.title,panels};
})()"""
def import_episode(ep):
    folder=episode_path(ep);mp,m=load_manifest(ep)
    page=folder/(ep+'_reader.html')
    signatures=[digest(mp),digest(page),'importer-9']
    for c in m.get('cuts',[]):
        if c.get('asset'):
            asset=(folder/c['asset']).resolve()
            if not asset.is_relative_to(ROOT.resolve()):raise ValueError('Asset outside project')
            signatures.append(digest(asset))
    key=hashlib.sha256('|'.join(signatures).encode()).hexdigest()
    CACHE.mkdir(parents=True,exist_ok=True);cached=CACHE/(ep+'_'+key+'.json')
    with LOCK:
        if cached.exists():return json.loads(cached.read_text(encoding='utf-8'))
        sys.path.insert(0,str(ROOT/'episodes'/'EP03'/'review'))
        from cdp import Chrome
        browser=Chrome(CACHE/'chrome_import',760,1000)
        try:browser.navigate(page);data=browser.evaluate(EXTRACT)
        finally:browser.close()
        assets={};cuts={c['cut_id']:c for c in m.get('cuts',[])}
        for p in data['panels']:
            c=cuts.get(p['id'],{})
            p['source']={k:copy.deepcopy(v) for k,v in c.items() if k not in ['lettering','state','sequence_state']}
            for l in p['layers']:
                if l['type']!='image':continue
                aid=ep+'-'+p['id']+'-'+l['id']
                original=(folder/l['path']).resolve()
                if not original.is_relative_to(ROOT.resolve()):raise ValueError('Image outside project')
                if ep!='EP01':
                    raw=original.read_bytes()
                    import mimetypes
                    mime=mimetypes.guess_type(original.name)[0] or 'image/webp'
                    l['src']='data:'+mime+';base64,'+base64.b64encode(raw).decode()
                else:
                    raw=base64.b64decode(l['src'].split(',',1)[1]);mime=l['src'].split(';',1)[0][5:]
                assets[aid]={'id':aid,'src':l.pop('src'),'mime':mime,'width':l.pop('width'),'height':l.pop('height'),'originalPath':str((folder/l.pop('path')).relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(raw).hexdigest()}
                l['assetId']=aid;l['bakedText']=ep=='EP01'
                l['preserveAspectRatio']=True
        doc={'schemaVersion':SCHEMA,'id':str(uuid.uuid4()),'title':data['title'],'episode':ep,'canvasWidth':1080,'bakedText':ep=='EP01','warnings':(['EP01 original dialogue is baked into the art. Use region annotation/redraw; existing baked text cannot be moved separately.'] if ep=='EP01' else []),'assets':assets,'panels':data['panels'],'directives':{'preserveStyle':True,'sourceFidelity':True,'notes':''},'baseline':{'episode':ep,'manifestPath':str(mp.relative_to(ROOT)).replace('\\','/'),'manifestSha256':digest(mp),'originalPanelIds':list(cuts),'panels':copy.deepcopy(data['panels']),'styleRefs':['references/adopted_v03/ep01_01.webp','references/adopted_v03/ep01_04.webp'],'sourceRanges':m.get('source_ranges',m.get('source_range',[]))},'deletedPanels':[],'createdAt':now(),'updatedAt':now()}
        cached.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
        return doc
if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('episode',nargs='?');args=a.parse_args()
    if args.episode:
        d=import_episode(args.episode);print(json.dumps({'episode':args.episode,'panels':len(d['panels']),'assets':len(d['assets']),'layers':sum(len(p['layers']) for p in d['panels'])}))
    else:print(json.dumps(catalog()))

