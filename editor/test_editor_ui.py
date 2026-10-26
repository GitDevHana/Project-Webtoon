"""Browser regression for editing, portability, persistence and local-edit handoff."""
from pathlib import Path
import sys,json,time,threading,base64,hashlib,shutil
from unittest.mock import patch
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'episodes/EP03/review'))
sys.path.insert(0,str(ROOT/'editor'))
from cdp import Chrome
import server
QA=ROOT/'editor/review';QA.mkdir(exist_ok=True)
DATA=QA/'test_data';DATA.mkdir(exist_ok=True)
class TestHandler(server.Handler):
 def do_POST(self):
  with patch('server.EDITOR',DATA):super().do_POST()
 def do_GET(self):
  if self.path.startswith('/api/saves'):
   with patch('server.EDITOR',DATA):super().do_GET()
  else:super().do_GET()
 def log_message(self,*args):pass
http=ThreadingHTTPServer(('127.0.0.1',0),TestHandler);http.save_lock=threading.Lock()
threading.Thread(target=http.serve_forever,daemon=True).start()
url='http://127.0.0.1:'+str(http.server_port)
checks=[]
def check(name,value):
 checks.append({'name':name,'pass':bool(value)})
 print(('PASS ' if value else 'FAIL ')+name,flush=True)
 if not value:raise AssertionError(name)
b=Chrome(QA/'chrome_ui',1440,1000)
def js(code):return b.evaluate(code)
def click(selector):
 r=js("(()=>{const e=document.querySelector("+json.dumps(selector)+");if(!e)throw Error('Missing selector');e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()")
 for t in ['mousePressed','mouseReleased']:b.call('Input.dispatchMouseEvent',{'type':t,'x':r['x'],'y':r['y'],'button':'left','clickCount':1})
def fill(selector,text):
 js("document.querySelector("+json.dumps(selector)+").focus()")
 b.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'a','code':'KeyA','modifiers':2,'windowsVirtualKeyCode':65})
 b.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'a','code':'KeyA','modifiers':2,'windowsVirtualKeyCode':65})
 b.call('Input.insertText',{'text':text})
 b.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Tab','code':'Tab','windowsVirtualKeyCode':9})
 b.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Tab','code':'Tab','windowsVirtualKeyCode':9})
def drag(selector,dx,dy,offset=.5):
 r=js("(()=>{const e=document.querySelector("+json.dumps(selector)+");e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return {x:r.x+r.width*"+str(offset)+",y:r.y+r.height*"+str(offset)+"};})()")
 b.call('Input.dispatchMouseEvent',{'type':'mousePressed',**r,'button':'left','clickCount':1})
 for i in range(1,6):b.call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':r['x']+dx*i/5,'y':r['y']+dy*i/5,'buttons':1})
 b.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':r['x']+dx,'y':r['y']+dy,'button':'left','clickCount':1})
def file_input(selector,paths):
 node=b.call('DOM.getDocument')['root']['nodeId']
 target=b.call('DOM.querySelector',{'nodeId':node,'selector':selector})['nodeId']
 b.call('DOM.setFileInputFiles',{'nodeId':target,'files':[str(p.resolve()) for p in paths]})
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'episodes').glob('EP*/*manifest.json')}
try:
 b.call('Page.navigate',{'url':url})
 b.wait("!!document.querySelector('#episode option[value=EP04]')",20)
 check('catalog',js("document.querySelectorAll('#episode option').length===4"))
 click('#loadEpisode');b.wait("doc&&doc.panels.length===60&&!busy",30)
 check('project_prompt',js("doc.projectContext.files.some(f=>f.path==='PROMPT.md'&&f.text.length>1000)"))
 check('original_images',js("Object.values(doc.assets).every(a=>a.src.startsWith('data:image/'))"))
 b.screenshot(QA/'editor_loaded.png')
 image='#paper .panel-row:first-child .layer[data-type=image]'
 click(image);original=js("C.copy(selected())")
 drag(image,24,18,.7)
 check('drag_existing_image',js("Math.abs(selected().x-"+str(original['x'])+")>20"))
 check('drag_changed',js("dirty&&history.length>0"))
 click('#undo')
 check('undo_image_move',js("Math.abs(selected().x-"+str(original['x'])+")<.1"))
 click('#redo')
 check('redo_image_move',js("Math.abs(selected().x-"+str(original['x'])+")>20"))
 oldw=js('selected().w');drag('.layer.selected .handle[data-handle=se]',25,25)
 check('resize_image',js("Math.abs(selected().w-"+str(oldw)+")>10"))
 check('aspect_ratio',js("Math.abs(selected().w/selected().h-"+str(original['w']/original['h'])+")<.01"))
 click('#tools [data-tool=region]')
 drag('#paper .panel-row:first-child .panel-stage',90,80,.45)
 check('region_created',js("selected().type==='region'"))
 fill('#inspector textarea[data-key=notes]','Only restore the missing beard. Preserve face and composition.')
 check('local_edit_default',js("selected().editMode==='local_edit'"))
 check('region_request_saved_in_revision',js("C.revision(doc).changes.some(p=>p.regions.some(r=>r.request.includes('beard')&&r.editMode==='local_edit'))"))
 check('identity_policy',js("C.revision(doc).editPolicy.preserveSubjectIdentity&&C.revision(doc).directives.localizedEdits"))
 click('#addPanel');click('#paper .panel-row:first-child .panel-gap');check('insert_panel',js("doc.panels.length===61"))
 fill('#inspector textarea[data-target=panel]','Additional reaction image requested.')
 click('#tools [data-tool=text]');drag('.panel-row.active .panel-stage',180,80,.2)
 fill('#inspector textarea[data-key=text]','Edited dialogue')
 check('add_text_box',js("selected().type==='text'&&selected().text==='Edited dialogue'"))
 click('#inspector [data-action=duplicate]');check('duplicate_text_box',js("current().layers.filter(l=>l.type==='text').length===2"))
 click('#inspector [data-action=delete]');check('delete_layer',js("current().layers.filter(l=>l.type==='text').length===1"))
 click('#inspector [data-action=panelUp]');check('reorder_panels',js('doc.panels[0].originCutId===null'))
 fill('#inspector input[data-key=gapAfter]','245');check('gap_change',js('current().gapAfter===245'))
 click('#save');b.wait("!busy&&!dirty",25)
 saved=list((DATA/'saves').glob('*.wtedit.json'));check('save_to_disk',bool(saved))
 on_disk=json.loads(saved[-1].read_text(encoding='utf-8'))
 check('save_keeps_all_assets',len(on_disk['assets'])==js('Object.keys(doc.assets).length'))
 before=js('JSON.stringify(doc.panels)')
 click('#openSaves');b.wait("!!document.querySelector('[data-save-index]')",20)
 click('[data-save-index="0"]');b.wait("!busy&&!document.querySelector('#dialog').open",30)
 check('reopen_exact_layout',js('JSON.stringify(doc.panels)')==before)
 click('#finish');b.wait("!!document.querySelector('#dialog').open&&!busy",30)
 latest=json.loads((DATA/'handoff/latest.json').read_text(encoding='utf-8'))['EP04']
 rev=json.loads(Path(latest['revisionPath']).read_text(encoding='utf-8'))
 check('handoff_contains_prompt',any(f['path']=='PROMPT.md' for f in rev['projectContext']['files']))
 check('handoff_local_edit_only',rev['editPolicy']['default']=='local_edit')
 check('handoff_contains_added_panel',rev['summary']['addedPanels']==1)
 check('handoff_not_autogeneration',Path(latest['previewPath']).is_file())
 preview_path=Path(latest['previewPath']);click('#closeDialog')
 payload=js("C.exportReader(doc,{annotations:true})")
 check('embedded_document_roundtrip',js("(async()=>{const d=await C.importHTML(C.exportReader(doc));return JSON.stringify(d.panels)===JSON.stringify(doc.panels)})()"))
 asset=next(iter(on_disk['assets'].values()))['src']
 generic=QA/'other_story.html';prompt=QA/'PROMPT.md'
 generic.write_text('<!doctype html><html><head><title>Another story</title></head><body><main><section class="scene" data-cut="A001" id="A001"><img class="art" width="1080" height="720" src="'+asset+'"><div class="letter speech">A different story</div></section></main></body></html>',encoding='utf-8')
 prompt.write_text('Other project prompt: keep the angular line art and the original beard.',encoding='utf-8')
 file_input('#fileInput',[generic,prompt]);b.wait("doc&&doc.title==='Another story'&&!busy",30)
 check('external_project_import',js("doc.episode==='EP00'&&doc.panels.length===1"))
 check('external_prompt_not_previous_project',js("doc.projectContext.files.length===1&&doc.projectContext.files[0].text.includes('angular')&&!JSON.stringify(doc.projectContext).includes('projectWT')"))
 check('external_no_EP01_reference',js("!JSON.stringify(doc.baseline).includes('adopted_v03')"))
 click('#save');b.wait('!busy&&!dirty',25)
 file_input('#fileInput',[preview_path]);b.wait("doc&&doc.episode==='EP04'&&!busy",30)
 check('review_HTML_reopens',js("doc.panels.length===61&&doc.projectContext.files.some(f=>f.path==='PROMPT.md')"))
 click('#showContext');b.wait("!!document.querySelector('#dialog').open",5)
 check('context_view',js("document.querySelector('#dialogContent').textContent.includes('PROMPT.md')"))
 click('#closeDialog')
 click('#preview');check('preview_mode',js("document.body.classList.contains('preview-mode')"))
 click('#preview')
 for width in [1440,1100,820]:
  b.call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':False})
  js('fit()')
  check('layout_'+str(width),js("document.documentElement.scrollWidth<=innerWidth&&document.querySelector('#viewport').clientWidth>200"))
 check('original_manifests_unchanged',hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'episodes').glob('EP*/*manifest.json')})
except Exception as e:
 print('ERROR',repr(e),flush=True)
 try:b.screenshot(QA/'editor_failure.png');print('STATE',js("({title:doc?.title,pid,lid,tool,busy,dirty,toast:document.querySelector('#toast').textContent})"))
 except:pass
 raise
finally:
 (QA/'ui_results.json').write_text(json.dumps({'checks':checks,'passed':sum(c['pass'] for c in checks),'failed':sum(not c['pass'] for c in checks)},ensure_ascii=False,indent=2),encoding='utf-8')
 b.close();http.shutdown();http.server_close()
