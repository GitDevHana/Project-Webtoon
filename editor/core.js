/* projectWT editor document and renderer. Local, no dependencies. */
(function(g){
'use strict';
const SCHEMA='projectWT.editor/1',W=1080;
const uid=p=>p+'_'+(globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+Math.random().toString(36).slice(2,8));
const copy=x=>JSON.parse(JSON.stringify(x));
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=0)=>Number.isFinite(+v)?+v:d;
const clamp=(n,a,b)=>Math.min(b,Math.max(a,n));
function emptyDoc(){return {schemaVersion:SCHEMA,id:uid('doc'),title:'새 회차',episode:'EP00',canvasWidth:W,assets:{},panels:[],deletedPanels:[],directives:{preserveStyle:true,sourceFidelity:true,notes:''},baseline:{originalPanelIds:[],panels:[]},createdAt:new Date().toISOString()};}
function layer(type,more={}){
 return {id:uid(type),type,x:100,y:100,w:type==='balloon'?600:500,h:type==='balloon'?230:250,rotation:0,opacity:1,locked:false,hidden:false,text:'',fontSize:52,color:'#29251e',fill:type==='region'?'transparent':'#ffffff',stroke:type==='region'?'#e57439':'#29251e',strokeWidth:type==='region'?5:3,align:'center',shape:'ellipse',speaker:'LEON',tail:{x:.3,y:1.13},...more};
}
function panel(more={}){return {id:uid('NEW'),originCutId:null,title:'새 콘티',height:1000,gapAfter:100,background:'#ffffff',notes:'',redraw:true,reviewed:false,layers:[],...more};}
function normalize(d){
 if(!d||d.schemaVersion!==SCHEMA||!Array.isArray(d.panels)||!d.assets||typeof d.assets!=='object')throw Error('projectWT 편집 파일이 아닙니다. 회차 HTML 또는 .wtedit.json을 선택하세요.');
 if(d.panels.length>1000)throw Error('한 번에 1,000컷까지 불러올 수 있습니다.');
 d.canvasWidth=W;d.id=d.id||uid('doc');d.episode=/^EP\d{2,3}$/.test(d.episode)?d.episode:'EP00';d.deletedPanels=d.deletedPanels||[];d.directives={preserveStyle:true,sourceFidelity:true,notes:'',...d.directives};d.baseline=d.baseline||{panels:copy(d.panels),originalPanelIds:d.panels.map(p=>p.id)};
 if(!d.baseline.panels)d.baseline.panels=copy(d.panels);
 d.assets=Object.fromEntries(Object.entries(d.assets).map(([id,a])=>[id,typeof a==='string'?{id,src:a}:a]));
 const ids=new Set();
 for(const p of d.panels){
  if(!p.id||ids.has(p.id))p.id=uid('cut');ids.add(p.id);
  p.height=clamp(num(p.height,1000),1,1000000);p.gapAfter=clamp(num(p.gapAfter,90),0,5000);p.background=p.background||'#fff';p.notes=String(p.notes||'');p.layers=p.layers||[];p.redraw=!!p.redraw;
  for(const l of p.layers){
   l.id=l.id||uid(l.type);l.x=num(l.x);l.y=num(l.y);l.w=clamp(num(l.w,500),8,6000);l.h=clamp(num(l.h,250),.1,1000000);l.rotation=num(l.rotation);l.opacity=clamp(num(l.opacity,1),0,1);
   if(!['image','balloon','text','stroke','rect','region','arrow'].includes(l.type))throw Error('지원하지 않는 레이어 종류: '+l.type);
   if(l.type==='image'&&(!d.assets[l.assetId]||!/^data:image\/(png|jpeg|webp|gif|svg\+xml);/i.test(d.assets[l.assetId].src||'')))throw Error('그림 데이터가 빠졌거나 외부 링크입니다: '+p.id);
  }
 }
 return d;
}
function snapshot(d){return copy({panels:d.panels,deletedPanels:d.deletedPanels,directives:d.directives,title:d.title,projectContext:d.projectContext,projectContext:d.projectContext});}
function restore(d,s){Object.assign(d,copy(s));return d;}
function wrapText(text,size,width){
 const chars=Math.max(5,Math.floor(width/size));let out=[];
 for(const line of String(text).split('\n')){
  let current='';
  for(const token of line.split(/(\s+)/)){if(current.length+token.length>chars&&current){out.push(current.trimEnd());current='';}if(token.length>chars){for(const ch of token){if(current.length>=chars){out.push(current);current='';}current+=ch;}}else current+=token;}
  out.push(current.trimEnd());
 }
 return out;
}
function shapeSVG(l){
 const w=l.w,h=l.h,sw=num(l.strokeWidth,3),fill=esc(l.fill||'#fff'),stroke=esc(l.stroke||'#29251e'),drawingWidth=l.pathWidth||Math.max(8,...(l.points||[[w,h]]).map(p=>p[0])),drawingHeight=l.pathHeight||Math.max(8,...(l.points||[[w,h]]).map(p=>p[1]));
 if(l.type==='balloon'){
  const tx=clamp(num(l.tail?.x,.3),-.5,1.5)*w,ty=num(l.tail?.y,1.13)*h;
  const tail=l.shape==='box'?'':'<path d="M '+(w*.28)+' '+(h*.82)+' L '+tx+' '+ty+' L '+(w*.42)+' '+(h*.88)+'" fill="'+fill+'" stroke="'+stroke+'" stroke-width="'+sw+'" stroke-linejoin="round"/>';
  const body=l.shape==='box'?'<rect x="'+sw+'" y="'+sw+'" width="'+(w-2*sw)+'" height="'+(h-2*sw)+'" rx="12" fill="'+fill+'" stroke="'+stroke+'" stroke-width="'+sw+'"/>':'<ellipse cx="'+w/2+'" cy="'+h/2+'" rx="'+(w/2-sw)+'" ry="'+(h/2-sw)+'" fill="'+fill+'" stroke="'+stroke+'" stroke-width="'+sw+'"/>';
  return '<svg class="bubble-shape" width="100%" height="100%" viewBox="0 0 '+w+' '+h+'" style="overflow:visible">'+tail+body+'</svg>';
 }
 if(l.type==='arrow'){
  const pts=l.points||[[0,h],[w,0]],a=pts[0],b=pts[pts.length-1],angle=Math.atan2(b[1]-a[1],b[0]-a[0]),head=Math.min(42,Math.max(14,Math.hypot(b[0]-a[0],b[1]-a[1])*.25)),x1=b[0]-head*Math.cos(angle-.5),y1=b[1]-head*Math.sin(angle-.5),x2=b[0]-head*Math.cos(angle+.5),y2=b[1]-head*Math.sin(angle+.5);
  return '<svg width="100%" height="100%" viewBox="0 0 '+drawingWidth+' '+drawingHeight+'" preserveAspectRatio="none" style="overflow:visible"><path d="M '+a[0]+' '+a[1]+' L '+b[0]+' '+b[1]+' M '+x1+' '+y1+' L '+b[0]+' '+b[1]+' L '+x2+' '+y2+'" fill="none" stroke="'+stroke+'" stroke-width="'+sw+'" stroke-linecap="round" stroke-linejoin="round"/></svg>';
 }
 if(l.type==='stroke'){
  const pts=l.points||[],d=pts.map((p,i)=>(i?'L':'M')+' '+num(p[0])+' '+num(p[1])).join(' ');
  return '<svg width="100%" height="100%" viewBox="0 0 '+drawingWidth+' '+drawingHeight+'" preserveAspectRatio="none" style="overflow:visible"><path d="'+d+'" fill="none" stroke="'+stroke+'" stroke-width="'+sw+'" stroke-linecap="round" stroke-linejoin="round"/></svg>';
 }
 return '<svg width="100%" height="100%" viewBox="0 0 '+w+' '+h+'" style="overflow:visible"><rect x="'+sw/2+'" y="'+sw/2+'" width="'+(w-sw)+'" height="'+(h-sw)+'" rx="3" fill="'+fill+'" stroke="'+stroke+'" stroke-width="'+sw+'" '+(l.type==='region'?'stroke-dasharray="18 10"':'')+'/></svg>';
}
function layerMarkup(l,d,annotations=false){
 if(l.hidden||(l.type==='region'||l.annotation)&&!annotations)return '';
 let inside='';
 if(l.type==='image'){
  const a=d.assets[l.assetId];if(!a)return '';
  if(l.crop){const c=l.crop;inside='<svg role="img" aria-label="'+esc(l.alt||'원본 그림의 이어진 구간')+'" width="100%" height="100%" viewBox="'+c.x+' '+c.y+' '+c.w+' '+c.h+'" preserveAspectRatio="none"><image href="'+esc(a.src)+'" width="'+a.width+'" height="'+a.height+'"/></svg>';}else inside='<img draggable="false" src="'+esc(a.src)+'" alt="'+esc(l.alt||'웹툰 그림')+'" style="width:100%;height:100%;object-fit:contain;display:block">';
 }else if(['balloon','rect','region','stroke','arrow'].includes(l.type))inside=shapeSVG(l);
 if(l.type==='balloon'||l.type==='text'){
  if(l.type==='text'&&l.box)inside=shapeSVG({...l,type:'rect'});
  const pad=l.type==='balloon'?'10% 8%':l.box?'18px':'0';
  inside+='<div class="layer-text" style="position:absolute;inset:0;display:flex;align-items:'+(l.type==='text'&&l.box?'flex-start':'center')+';justify-content:'+({left:'flex-start',right:'flex-end'}[l.align]||'center')+';padding:'+pad+';font-size:'+num(l.fontSize,52)+'px;line-height:1.5;color:'+esc(l.color||'#29251e')+';font-weight:'+(l.bold?'700':'400')+';text-align:'+esc(l.align||'center')+';white-space:pre-wrap;word-break:keep-all;overflow-wrap:anywhere">'+esc(l.text)+'</div>';
 }
 if(l.type==='region'&&annotations)inside+='<span class="request-tag">수정 요청</span><div class="request-caption">'+esc(l.notes||'영역 선택 후 수정 내용을 적으세요')+'</div>';
 const owner=d.panels?.find(p=>p.layers?.includes(l)),depth=owner?owner.layers.indexOf(l):0;
 return '<div class="layer" data-layer="'+esc(l.id)+'" data-type="'+l.type+'" data-annotation="'+!!l.annotation+'" style="position:absolute;z-index:'+depth+';left:'+l.x+'px;top:'+l.y+'px;width:'+l.w+'px;height:'+l.h+'px;transform:rotate('+num(l.rotation)+'deg);opacity:'+num(l.opacity,1)+';'+(l.locked?'cursor:default;':'')+'">'+inside+'</div>';
}
function revision(d){
 const before=new Map((d.baseline.panels||[]).map(p=>[p.id,p])),currentIds=d.panels.map(p=>p.id),baseIds=d.baseline.originalPanelIds||[...before.keys()];
 let changes=[];
 for(let i=0;i<d.panels.length;i++){
  const p=d.panels[i],b=before.get(p.id),layerChanges=[];
  if(b){
   const old=new Map((b.layers||[]).map(l=>[l.id,l]));
   for(const l of p.layers){const was=old.get(l.id);if(!was)layerChanges.push({operation:'add_layer',layer:copy(l)});else if(JSON.stringify(l)!==JSON.stringify(was))layerChanges.push({operation:'update_layer',layerId:l.id,before:copy(was),after:copy(l)});old.delete(l.id);}
   for(const [id,l]of old)layerChanges.push({operation:'delete_layer',layerId:id,before:copy(l)});
  }
  const regions=p.layers.filter(l=>l.type==='region').map(l=>({id:l.id,rect:{x:l.x,y:l.y,w:l.w,h:l.h},rotation:l.rotation,request:l.notes||'',editMode:l.editMode||'local_edit',preserveSubjectIdentity:true,preserveComposition:true,targetLayerIds:l.targetLayerIds||[]}));
  const geometryChanged=b&&['height','gapAfter','background'].some(k=>b[k]!==p[k]);
  const layerOrder=p.layers.map(l=>l.id),layerOrderChanged=!!b&&JSON.stringify(layerOrder)!==JSON.stringify((b.layers||[]).map(l=>l.id));
  if(!b||layerChanges.length||geometryChanged||layerOrderChanged||p.notes||p.redraw||p.reviewed)changes.push({panelId:p.id,originCutId:p.originCutId||null,order:i+1,operation:!b?'add_panel':'update_panel',source:p.source||null,title:p.title,notes:p.notes||'',redraw:!!p.redraw,reviewed:!!p.reviewed,geometry:{height:p.height,gapAfter:p.gapAfter,background:p.background},layoutSplit:!!p.layoutSplit,isSpacer:!!p.isSpacer,artworkAction:p.artworkAction||null,layerOrder,layerOrderChanged,regions,annotations:p.layers.filter(l=>l.annotation||['arrow','stroke'].includes(l.type)).map(l=>copy(l)),layerChanges:!b?p.layers.map(l=>({operation:'add_layer',layer:copy(l)})):layerChanges,hasSketch:p.layers.some(l=>l.type==='stroke'),needsArtwork:!!p.redraw||!b&&!p.layoutSplit&&!p.isSpacer&&!p.layers.some(l=>l.type==='image')||regions.some(r=>r.request.trim())});
 }
 const deletions=baseIds.filter(id=>!currentIds.includes(id)).map(id=>({panelId:id,source:before.get(id)?.source||null,operation:'delete_panel'}));
 return {schemaVersion:'projectWT.revision/1',documentId:d.id,episode:d.episode,title:d.title,createdAt:new Date().toISOString(),status:'human_edits_ready_for_codex',baseline:copy({...d.baseline,panels:undefined}),directives:copy(d.directives),projectContext:copy(d.projectContext||null),editPolicy:{default:'local_edit',preserveSubjectIdentity:true,preserveComposition:true,additionalArtworkOnlyWhenRequested:true},panelOrder:currentIds,orderChanged:JSON.stringify(baseIds.filter(id=>currentIds.includes(id)))!==JSON.stringify(currentIds.filter(id=>baseIds.includes(id))),changes,deletions,summary:{totalPanels:d.panels.length,changedPanels:changes.length,addedPanels:changes.filter(c=>c.operation==='add_panel').length,deletedPanels:deletions.length,redrawPanels:changes.filter(c=>c.needsArtwork).length},applyInstructions:['Read project AGENTS.md, PROMPT.md and memory before applying.','Read the latest project instructions and original source. Preserve the current project style and subject identity.','Keep placement and dialogue edits as shown. Edit existing images locally: change only the requested feature or region, preserving the rest, including face, pose, expression, composition and subject form except changes explicitly requested by the user. Additional artwork requires an explicit request.','Region rectangles, pen sketches, arrows and annotation text boxes are human directions, not final artwork. Interpret the text and pointer targets together. Layout-only image slices retain the original asset and must not trigger regeneration. Do not count spacers, slices or placeholders as new narrative shots.','Do not silently invent source events. Record conflicts and resolve with the user when materially necessary.','Review whole episode and mobile, deliver HTML and manifest.']};
}
function exportReader(d,{annotations=false,embedDocument=true}={}){
 const content=d.panels.map((p,i)=>'<section class="reader-panel" data-cut="'+esc(p.id)+'" style="position:relative;width:1080px;height:'+p.height+'px;margin-bottom:'+p.gapAfter+'px;background:'+esc(p.background)+'">'+p.layers.map(l=>layerMarkup(l,d,annotations)).join('')+(annotations&&p.notes?'<aside class="panel-note">'+esc(p.notes)+'</aside>':'')+'</section>').join('');
 const embedded=embedDocument?'<script type="application/json" id="wt-edit-document">'+JSON.stringify(d).replace(/</g,'\\u003c')+'</script>':'';
 return '<!doctype html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(d.episode+' '+d.title)+'</title><style>*{box-sizing:border-box}body{margin:0;background:#eeeae2;font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif}.reader-wrap{margin:auto;max-width:720px;overflow:hidden;background:#fff}.reader{width:1080px;transform-origin:top left}.layer img{user-select:none}.layer-text{font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif}.bubble-shape{position:absolute;inset:0}.request-tag{position:absolute;top:-38px;left:0;background:#e57439;color:#fff;font-size:26px;padding:3px 12px}.request-caption{position:absolute;top:100%;left:0;width:100%;font-size:30px;color:#b94b19;background:#fff5e9;padding:10px}.panel-note{position:absolute;bottom:0;left:0;background:#fff3de;color:#9e4d20;font-size:32px;padding:12px;white-space:pre-wrap}.end{text-align:center;font-size:45px;padding:75px 0}</style></head><body><div class="reader-wrap"><main class="reader">'+content+'<footer class="end">'+esc(d.episode==='EP00'?d.title:d.episode.replace('EP',''))+'화 편집본 끝</footer></main></div>'+embedded+'<script>(function(){const r=document.querySelector(".reader"),w=document.querySelector(".reader-wrap");function fit(){let z=w.clientWidth/1080;r.style.zoom=z}addEventListener("resize",fit);fit()})();</script></body></html>';
}
async function importHTML(html,name='회차'){
 const dom=new DOMParser().parseFromString(html,'text/html'),embedded=dom.getElementById('wt-edit-document');
 if(embedded)return normalize(JSON.parse(embedded.textContent));
 const scenes=[...dom.querySelectorAll('.scene[data-cut],.scene[id]')].filter(s=>s.querySelector('img.art, img'));
 if(!scenes.length)throw Error('분리된 그림을 찾지 못했습니다. 회차 목록에서 불러오거나 편집 JSON을 선택하세요.');
 const d=emptyDoc();d.episode=name.match(/EP\d{2,3}/i)?.[0].toUpperCase()||'EP00';d.title=dom.querySelector('title')?.textContent||name;
 let ai=0;
 for(const s of scenes){
  const im=s.querySelector('img.art,img'),src=im.getAttribute('src')||'';
  if(!src.startsWith('data:image/'))throw Error('그림이 포함된 _scroll.html을 선택하세요. 상대경로 reader 파일은 회차 목록에서 불러오세요.');
  const natural=new Image();natural.src=src;await natural.decode();const iw=natural.naturalWidth,ih=natural.naturalHeight;if(!iw||!ih)throw Error('그림 크기를 읽을 수 없습니다.');const frac=s.classList.contains('insert')?.64:s.classList.contains('small')?.76:s.classList.contains('normal')?.94:1,w=W*frac;
  const p=panel({id:s.id||uid('cut'),originCutId:s.id,title:im.alt||s.id,redraw:false,layers:[],gapAfter:s.classList.contains('short')?75:s.classList.contains('wide-gap')?320:s.classList.contains('transition-gap')?450:190});
  const nodes=[...s.querySelectorAll('.letter')],imageIndex=[...s.querySelectorAll('*')].indexOf(im);let y=0;
  function textLayer(el){const type=el.classList.contains('speech')?'balloon':'text',text=el.textContent.replace(/\r/g,'');const lines=wrapText(text,52,760).length,h=Math.max(type==='balloon'?180:85,lines*78+(type==='balloon'?85:15)),isP=el.dataset.speaker==='PRIN',l=layer(type,{x:isP?220:55,y,w:805,h,text,speaker:el.dataset.speaker||'LEON',fontSize:52,fill:'#fff',shape:'ellipse'});p.layers.push(l);y+=h+65;}
  nodes.filter(n=>[...s.querySelectorAll('*')].indexOf(n)<imageIndex).forEach(textLayer);
  const aid='image_'+(++ai);d.assets[aid]={id:aid,src,mime:'image/webp',width:iw,height:ih};p.layers.push(layer('image',{x:(W-w)/2,y,w,h:w*ih/iw,assetId:aid,alt:im.alt,originalAspect:iw/ih}));y+=w*ih/iw+60;
  nodes.filter(n=>[...s.querySelectorAll('*')].indexOf(n)>imageIndex).forEach(textLayer);
  p.height=Math.ceil(y);d.panels.push(p);
 }
 d.baseline={episode:d.episode,importedFrom:name,originalPanelIds:d.panels.map(p=>p.id),panels:copy(d.panels),styleRefs:[],note:'HTML import; source manifest not supplied. Verify original source before redraw.'};
 return normalize(d);
}
g.WTCore={SCHEMA,W,uid,copy,esc,num,clamp,emptyDoc,layer,panel,normalize,snapshot,restore,wrapText,shapeSVG,layerMarkup,revision,exportReader,importHTML};
})(typeof window!=='undefined'?window:globalThis);


