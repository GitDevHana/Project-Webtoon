"""Backend regression checks; uses original episodes read-only and new test saves."""
import sys,json,threading,urllib.request,urllib.error,unittest,hashlib,uuid,shutil
from unittest.mock import patch
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parent))
import server,importer
class BackendTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.hashes={str(p):importer.digest(p) for p in (importer.ROOT/'episodes').glob('EP*/*manifest.json')}
  cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.http.save_lock=threading.Lock()
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start();cls.url='http://127.0.0.1:'+str(cls.http.server_port)
 @classmethod
 def tearDownClass(cls):
  cls.http.shutdown();cls.http.server_close()
  assert cls.hashes=={str(p):importer.digest(p) for p in (importer.ROOT/'episodes').glob('EP*/*manifest.json')}
 def request(self,path,data=None):
  req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data else None,headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req) as r:return json.load(r)
 def test_catalog(self):
  v=self.request('/api/episodes');self.assertEqual([x['id'] for x in v['episodes']],['EP01','EP02','EP03','EP04'])
 def test_episode_imports(self):
  for ep,count in [('EP01',60),('EP02',58),('EP03',63),('EP04',60)]:
   d=self.request('/api/episodes/'+ep)
   expected=len(importer.load_manifest(ep)[1]['cuts']);self.assertEqual(len(d['panels']),expected)
   self.assertEqual(len(d['baseline']['panels']),expected)
   if ep!='EP01':self.assertEqual(expected,count)
   for panel in d['panels']:
    self.assertEqual(panel['width'],1080)
    self.assertTrue(panel['height']>0)
    for layer in panel['layers']:
     self.assertFalse(layer['locked'])
     if layer['type']=='image':self.assertTrue(d['assets'][layer['assetId']]['src'].startswith('data:image/'))
   if ep=='EP01':
    self.assertTrue(d['bakedText'])
    self.assertEqual(len(d['assets']),sum(1 for p in d['panels'] for l in p['layers'] if l['type']=='image'))
 def test_paths(self):
  for path in ['/../PROMPT.md','/%2e%2e/PROMPT.md','/project/episodes/../../PROMPT.md','/project/source/private.txt','/project/episodes/%2e%2e/%2e%2e/PROMPT.md','/cache/chrome_import/Preferences','/project/episodes/..%5c..%5cPROMPT.md']:
   with self.assertRaises(urllib.error.HTTPError) as ctx:self.request(path)
   self.assertEqual(ctx.exception.code,403)
 def test_save_roundtrip(self):
  d={'schemaVersion':importer.SCHEMA,'episode':'EP04','panels':[],'assets':{},'testOnly':True}
  result=self.request('/api/save',{'document':d,'name':'../../PROMPT.md'})
  p=Path(result['path'])
  try:self.assertTrue(p.is_relative_to(importer.EDITOR/'saves'));self.assertEqual(json.loads(p.read_text(encoding='utf-8')),d)
  finally:p.unlink()
 def test_handoff_and_autosave_separation(self):
  folder=(importer.EDITOR/('backend_test_'+uuid.uuid4().hex)).resolve()
  self.assertTrue(folder.is_relative_to(importer.EDITOR.resolve()))
  d={'schemaVersion':importer.SCHEMA,'id':'backend-test-document','episode':'EP04','panels':[],'assets':{},'projectContext':{'projectRoot':str(importer.ROOT)},'baseline':{'manifestPath':'episodes/EP04/EP04_manifest.json'}}
  try:
   with patch('server.EDITOR',folder):
    self.request('/api/save',{'document':d})
    self.assertFalse((folder/'handoff/latest.json').exists())
    revision={'episode':'EP04','instructions':[{'cutId':'C001','note':'test redraw'}]}
    result=self.request('/api/handoff',{'document':d,'revision':revision,'previewHtml':'<!doctype html><p>test preview</p>'})
    self.assertEqual(json.loads(Path(result['revisionPath']).read_text(encoding='utf-8')),revision)
    self.assertIn('test preview',Path(result['previewPath']).read_text(encoding='utf-8'))
    index=json.loads((folder/'handoff/latest.json').read_text(encoding='utf-8'))
    self.assertEqual(index['EP04']['documentPath'],result['documentPath'])
    self.assertTrue((Path(result['directory'])/'README_APPLY.md').exists())
  finally:
   if folder.exists():shutil.rmtree(folder)
 def test_invalid_document(self):
  with self.assertRaises(urllib.error.HTTPError) as c:self.request('/api/save',{'document':{}})
  self.assertEqual(c.exception.code,400)
if __name__=='__main__':unittest.main(verbosity=2)


