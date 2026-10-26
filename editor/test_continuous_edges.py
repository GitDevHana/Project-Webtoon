"""Continuous manuscript tests: real pointer input plus roundtrip and pixel-preserving slices."""
from pathlib import Path
import sys,json,base64,threading,hashlib
from unittest.mock import patch
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(ROOT/'editor'),str(ROOT/'episodes/EP03/review')]
import server
from cdp import Chrome
QA=ROOT/'editor/review/continuous_edges';QA.mkdir(parents=True,exist_ok=True)
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
def probe(name,value):
 checks.append({'name':name,'pass':bool(value)});print(('PASS ' if value else 'FAIL ')+name,flush=True)
try:
 b.call('Page.navigate',{'url':'http://127.0.0.1:'+str(http.server_port)})
 b.wait("typeof insertManuscriptSpace==='function'",15)
 svg='<svg xmlns="http://www.w3.org/2000/svg" width="300" height="900"><rect width="300" height="900" fill="#aa3311"/></svg>'
 src='data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()
 js('window.edgeAsset='+json.dumps(src))
 js("""window.edgeFixture=()=>{let d=C.emptyDoc();d.title='Edge checks';d.assets.art={id:'art',src:edgeAsset,width:300,height:900};d.panels=[C.panel({id:'first',height:600,gapAfter:120,redraw:false,layers:[C.layer('image',{id:'image1',assetId:'art',x:200,y:0,w:200,h:600})]}),C.panel({id:'second',height:600,gapAfter:0,redraw:false,layers:[C.layer('image',{id:'image2',assetId:'art',x:200,y:0,w:200,h:600})]})];d.baseline={panels:C.copy(d.panels),originalPanelIds:d.panels.map(p=>p.id)};adopt(d);setZoom(.6)};edgeFixture();""")
 js("""{let l=C.layer('arrow',{id:'arrow1',x:500,y:150,w:160,h:120,points:[[0,0],[160,120]],annotation:true});doc.panels[0].layers.push(l);render();select('first','arrow1')}""")
 before=js("document.querySelector('[data-layer=arrow1] path').getBoundingClientRect().width")
 drag('[data-layer=arrow1] .handle[data-handle=se]',60,40)
 after=js("document.querySelector('[data-layer=arrow1] path').getBoundingClientRect().width")
 probe('drawing_resizes_on_screen',after>before*1.3)
 js("select('first','arrow1');stack(-1)")
 probe('back_front_matches_export',js("""(()=>{let a=document.querySelector('[data-layer=arrow1]'),im=document.querySelector('[data-layer=image1]'),html=new DOMParser().parseFromString(C.exportReader(doc,{annotations:true}),'text/html'),ea=html.querySelector('[data-layer=arrow1]'),ei=html.querySelector('[data-layer=image1]');return Number(getComputedStyle(a).zIndex)<Number(getComputedStyle(im).zIndex)&&a.style.zIndex===ea.style.zIndex&&im.style.zIndex===ei.style.zIndex})()"""))
 js("""edgeFixture();doc.panels[0].layers[0].w=300;doc.panels[0].layers[0].h=600;render();insertManuscriptSpace('first',300,100,false)""")
 probe('contain_geometry_preserved_during_split',js("""(()=>{let layers=doc.panels.filter(p=>p.id==='first'||p.layoutSplit).flatMap(p=>p.layers).filter(l=>l.type==='image');return layers.length===2&&layers.every(l=>Math.abs(l.w-200)<.01&&Math.abs(l.x-250)<.01)})()"""))
 js("edgeFixture()")
 drag('[data-layer=image2]',0,-30)
 probe('drag_up_consumes_previous_gap',js("doc.panels[0].gapAfter<119&&flowTop('second')<719&&doc.panels[1].layers[0].y===0"))
finally:
 (QA/'results.json').write_text(json.dumps({'passed':sum(c['pass'] for c in checks),'failed':sum(not c['pass'] for c in checks),'checks':checks},indent=2),encoding='utf-8')
 b.close();http.shutdown();http.server_close()

if any(not c['pass'] for c in checks):raise AssertionError('Continuous edge check failed')
