"""Continuous manuscript tests: real pointer input plus roundtrip and pixel-preserving slices."""
from pathlib import Path
import sys,json,base64,threading,hashlib
from unittest.mock import patch
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(ROOT/'editor'),str(ROOT/'episodes/EP03/review')]
import server
from cdp import Chrome
QA=ROOT/'editor/review/continuous';QA.mkdir(parents=True,exist_ok=True)
DATA=QA/'data';DATA.mkdir(exist_ok=True)
class Handler(server.Handler):
 def do_POST(self):
  with patch('server.EDITOR',DATA):super().do_POST()
 def do_GET(self):
  if self.path.startswith('/api/saves'):
   with patch('server.EDITOR',DATA):super().do_GET()
  else:super().do_GET()
 def log_message(self,*a):pass
http=ThreadingHTTPServer(('127.0.0.1',0),Handler);http.save_lock=threading.Lock()
threading.Thread(target=http.serve_forever,daemon=True).start()
b=Chrome(QA/'chrome',1440,1000);checks=[]
def js(code):return b.evaluate(code)
def check(name,value):
 checks.append({'name':name,'pass':bool(value)});print(('PASS ' if value else 'FAIL ')+name,flush=True)
 if not value:raise AssertionError(name)
def point(selector,fx=.5,fy=.5):
 return js("(()=>{let e=document.querySelector("+json.dumps(selector)+");e.scrollIntoView({block:'center'});let r=e.getBoundingClientRect();return {x:r.x+r.width*"+str(fx)+",y:r.y+r.height*"+str(fy)+"}})()")
def mouse(kind,p):
 b.call('Input.dispatchMouseEvent',{'type':kind,**p,'button':'left','buttons':1 if kind=='mouseMoved' else 0,'clickCount':1})
def click(selector):
 q=point(selector);mouse('mousePressed',q);mouse('mouseReleased',q)
def drag(selector,dx,dy,fx=.5,fy=.5):
 q=point(selector,fx,fy);mouse('mousePressed',q)
 for i in range(1,8):mouse('mouseMoved',{'x':q['x']+dx*i/7,'y':q['y']+dy*i/7})
 mouse('mouseReleased',{'x':q['x']+dx,'y':q['y']+dy})
def fill(selector,text):
 click(selector)
 for kind in ['keyDown','keyUp']:b.call('Input.dispatchKeyEvent',{'type':kind,'key':'a','code':'KeyA','modifiers':2,'windowsVirtualKeyCode':65})
 b.call('Input.insertText',{'text':text})
 for kind in ['keyDown','keyUp']:b.call('Input.dispatchKeyEvent',{'type':kind,'key':'Tab','code':'Tab','windowsVirtualKeyCode':9})
try:
 b.call('Page.navigate',{'url':'http://127.0.0.1:'+str(http.server_port)})
 b.wait("typeof insertManuscriptSpace==='function'",15)
 check('unified_toolbar',js("!!document.querySelector('[data-tool=pen]')&&!!document.querySelector('[data-tool=arrow]')&&!document.querySelector('[data-tool=balloon]')"))
 svg='<svg xmlns="http://www.w3.org/2000/svg" width="300" height="900"><rect width="300" height="450" fill="#aa3311"/><rect y="450" width="300" height="450" fill="#2266aa"/></svg>'
 src='data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()
 js('window.fixtureImage='+json.dumps(src))
 js("""{let d=C.emptyDoc();d.title='Continuous QA';d.assets.original={id:'original',src:fixtureImage,width:300,height:900};d.panels=[C.panel({id:'first',title:'First',height:600,gapAfter:45,redraw:false,layers:[C.layer('image',{id:'art1',assetId:'original',x:200,y:30,w:150,h:450})]}),C.panel({id:'second',title:'Second',height:500,gapAfter:30,redraw:false,layers:[C.layer('image',{id:'art2',assetId:'original',x:200,y:20,w:150,h:450})]})];d.baseline={panels:C.copy(d.panels),originalPanelIds:['first','second']};adopt(d);setZoom(.6);}""")
 check('continuous_no_panel_headers',js("document.querySelectorAll('#paper .panel-head').length===0"))
 check('continuous_positions',js("Math.abs((stageFor('second').getBoundingClientRect().top-stageFor('first').getBoundingClientRect().top)/zoom-645)<.1"))
 drag('[data-layer=art1]',10,36)
 check('ripple_move',js("Math.abs(doc.panels[0].height-660)<.1&&Math.abs(doc.panels[0].layers[0].y-90)<.1&&Math.abs(flowTop('second')-705)<.1"))
 click('#undo');check('ripple_undo',js("doc.panels[0].height===600&&doc.panels[0].layers[0].y===30"))
 click('[data-tool=pen]');drag('[data-panel=first] .panel-stage',80,35,.45,.4)
 check('pen_points',js("selected().type==='stroke'&&selected().points.length>=6&&selected().annotation"))
 click('[data-tool=arrow]');drag('[data-panel=first] .panel-stage',-100,30,.65,.3)
 check('arrow_direction',js("selected().type==='arrow'&&selected().points[0][0]>selected().points[1][0]&&selected().annotation"))
 click('[data-tool=text]');drag('[data-panel=first] .panel-stage',170,70,.5,.65)
 fill('#inspector textarea[data-key=text]','Think bubble here <keep original> & restore beard.')
 check('unified_box',js("selected().type==='text'&&selected().box&&selected().annotation&&selected().text.includes('beard')"))
 check('annotation_hidden_in_clean_reader',js("C.layerMarkup(selected(),doc,false)===''&&C.layerMarkup(selected(),doc,true).includes('beard')"))
 js("window.preSplit=C.copy(doc);window.beforeHeight=doc.panels.reduce((s,p)=>s+p.height+p.gapAfter,0);insertManuscriptSpace('first',250,160,false)")
 check('insert_gap_in_image',js("doc.panels.length===4&&doc.panels[1].isSpacer&&doc.panels[1].height===160&&doc.panels[2].layoutSplit"))
 check('source_bytes_preserved',js("Object.keys(doc.assets).length===1&&doc.assets.original.src===fixtureImage"))
 check('crop_continuity',js("(()=>{let ls=doc.panels.filter(p=>p.id==='first'||p.layoutSplit).flatMap(p=>p.layers).filter(l=>l.type==='image');return ls.length===2&&Math.abs(ls[0].crop.h+ls[1].crop.h-900)<.01&&Math.abs(ls[1].crop.y-ls[0].crop.h)<.01})()"))
 check('gap_shifts_all_following_content',js("Math.abs(doc.panels.reduce((s,p)=>s+p.height+p.gapAfter,0)-beforeHeight-160)<.01"))
 check('layout_split_requires_no_new_art',js("C.revision(doc).changes.filter(p=>p.isSpacer||p.layoutSplit).every(p=>!p.needsArtwork)"))
 check('cropped_image_rendering',js("document.querySelectorAll('#paper .layer[data-type=image] svg[viewBox]').length===2"))
 b.screenshot(QA/'continuous_editor.png')
 click('#undo');check('split_undo',js("doc.panels.length===2&&!doc.panels[0].layers.find(l=>l.type==='image').crop"))
 js("insertManuscriptSpace('first',250,400,true)")
 check('new_cut_request',js("C.revision(doc).changes.filter(p=>p.artworkAction==='add_artwork'&&p.redraw).length===1"))
 check('pen_arrow_text_exported',js("C.revision(doc).changes.flatMap(p=>p.annotations).some(l=>l.type==='arrow')&&C.revision(doc).changes.flatMap(p=>p.annotations).some(l=>l.type==='stroke')&&C.revision(doc).changes.flatMap(p=>p.annotations).some(l=>l.box)"))
 check('export_import_exact',js("(async()=>{let d=await C.importHTML(C.exportReader(doc,{annotations:true}));return JSON.stringify(d.panels)===JSON.stringify(doc.panels)&&d.assets.original.src===fixtureImage})()"))
 click('#save');b.wait("!busy&&!dirty",20)
 saved=sorted((DATA/'saves').glob('*.wtedit.json'),key=lambda p:p.stat().st_mtime)[-1]
 check('disk_save_preserves_slices',json.loads(saved.read_text(encoding='utf-8'))['assets']['original']['src']==src)
 click('#finish');b.wait("!busy&&document.querySelector('#dialog').open",20)
 index=json.loads((DATA/'handoff/latest.json').read_text(encoding='utf-8'));item=index['document:'+js('doc.id')]
 rev=json.loads(Path(item['revisionPath']).read_text(encoding='utf-8'))
 check('handoff_has_sketches_and_pointer',any(l['type']=='stroke' for p in rev['changes'] for l in p['annotations']) and any(l['type']=='arrow' for p in rev['changes'] for l in p['annotations']))
 check('handoff_keeps_local_edit_policy',rev['editPolicy']['default']=='local_edit')
 tall=svg.replace('height="900"','height="30000"')
 tall_src='data:image/svg+xml;base64,'+base64.b64encode(tall.encode()).decode()
 js('window.tallSrc='+json.dumps(tall_src))
 check('long_whole_image_import',js("""(async()=>{let h='<html><title>Long strip</title><section class="scene" id="long"><img src="'+tallSrc+'"></section></html>';let d=await C.importHTML(h,'long.html');return d.panels.length===1&&d.panels[0].layers[0].h>100000})()"""))
 prompt=(ROOT/'PROMPT.md').read_text(encoding='utf-8')
 check('prompt_visual_tiers_and_text_kinds',all(s in prompt for s in ['4단계','데비','디엔','에스티아','thinker','thought','inner_narration','narration']))
except Exception:
 try:b.screenshot(QA/'failure.png');print('STATE',json.dumps(js("({pid,lid,tool,flow:flowGesture?.kind,toast:$('toast').textContent})"),ensure_ascii=True))
 except:pass
 raise
finally:
 (QA/'results.json').write_text(json.dumps({'passed':sum(c['pass'] for c in checks),'failed':sum(not c['pass'] for c in checks),'checks':checks},indent=2),encoding='utf-8')
 b.close();http.shutdown();http.server_close()
