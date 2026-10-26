"""Loopback-only projectWT editor server. Never modifies source episodes."""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import argparse,json,os,mimetypes,re,uuid,urllib.parse,threading,webbrowser,hashlib
from datetime import datetime,timezone
from importer import ROOT,EDITOR,SCHEMA,catalog,import_episode
MAX_BODY=150*1024*1024
def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()
def validate_document(value):
    if not isinstance(value,dict) or value.get('schemaVersion')!=SCHEMA:raise ValueError('Unsupported document schema')
    if not isinstance(value.get('panels'),list) or not isinstance(value.get('assets'),dict):raise ValueError('Missing panels/assets')
    if len(value['panels'])>3000:raise ValueError('Too many panels')
    return value
def safe_static(url):
    path=urllib.parse.unquote(urllib.parse.urlsplit(url).path)
    if '\x00' in path or '\\' in path:raise PermissionError('Invalid path')
    if path.startswith('/project/'):
        rel=path[len('/project/'):]
        if rel.split('/',1)[0] not in ('episodes','references'):raise PermissionError('Only episode/reference files are exposed')
        base=ROOT.resolve();target=(base/rel).resolve()
        allowed=[(base/'episodes').resolve(),(base/'references').resolve()]
        if not any(target.is_relative_to(a) for a in allowed):raise PermissionError('Path outside project assets')
    else:
        base=EDITOR.resolve();target=(base/path.lstrip('/')).resolve()
        if not target.is_relative_to(base):raise PermissionError('Path outside editor')
        if target==base:target=base/'index.html'
        if any(part in ('cache','handoff','saves') for part in target.relative_to(base).parts):raise PermissionError('Use save/import API or local files')
    return target
def saved_name(doc):
    ep=doc.get('episode','draft')
    if not re.fullmatch(r'EP[0-9]{2}',ep):ep='draft'
    return ep+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:8]
class Handler(BaseHTTPRequestHandler):
    server_version='ProjectWTEditor/1'
    def json(self,status,value):
        data=json.dumps(value,ensure_ascii=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        try:
            path=urllib.parse.urlsplit(self.path).path
            if path=='/api/health':return self.json(200,{'ok':True,'schemaVersion':SCHEMA,'projectRoot':str(ROOT)})

            if path=='/api/context':
                names=['AGENTS.md','PROMPT.md','memory/SERIES.md','memory/CHARACTERS.md','memory/LOCATIONS.md','memory/DECISIONS.md']
                files=[]
                for name in names:
                    p=ROOT/name
                    if p.is_file():
                        files.append({'path':name,'text':p.read_text(encoding='utf-8-sig'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
                return self.json(200,{'projectName':ROOT.name,'projectRoot':str(ROOT),'files':files,'capturedAt':datetime.now(timezone.utc).isoformat()})
            if path=='/api/saves':
                result=[]
                for p in sorted((EDITOR/'saves').glob('*.wtedit.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]:
                    meta=p.with_suffix('.meta.json')
                    value=json.loads(meta.read_text(encoding='utf-8')) if meta.exists() else {}
                    result.append({'name':p.name,'title':value.get('title',p.stem),'updatedAt':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(),'bytes':p.stat().st_size})
                return self.json(200,{'saves':result})
            if path.startswith('/api/saves/'):
                name=urllib.parse.unquote(path[len('/api/saves/'):])
                if not re.fullmatch(r'[A-Za-z0-9_.-]+\.wtedit\.json',name) or Path(name).name!=name:raise PermissionError('Invalid saved file name')
                return self.json(200,json.loads((EDITOR/'saves'/name).read_text(encoding='utf-8')))

            if path=='/api/episodes':return self.json(200,catalog())
            if re.fullmatch(r'/api/episodes/EP[0-9]{2}',path):return self.json(200,import_episode(path.rsplit('/',1)[1]))
            if path.startswith('/api/'):return self.json(404,{'error':'Unknown API'})
            target=safe_static(self.path)
            if not target.is_file():return self.json(404,{'error':'File not found'})
            data=target.read_bytes()
            self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(target.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(data)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
        except PermissionError as e:self.json(403,{'error':str(e)})
        except FileNotFoundError as e:self.json(404,{'error':'Episode source missing'})
        except Exception as e:self.json(500,{'error':str(e)})
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            expected='http://'+self.headers.get('Host','')
            if origin and origin!=expected:raise PermissionError('Cross-origin writes are refused')
            if self.headers.get_content_type()!='application/json':return self.json(415,{'error':'JSON content type required'})
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>MAX_BODY:return self.json(413,{'error':'Body size outside allowed range'})
            body=json.loads(self.rfile.read(length))
            doc=validate_document(body.get('document'));stem=saved_name(doc)
            path=urllib.parse.urlsplit(self.path).path
            if path=='/api/save':
                target=EDITOR/'saves'/(stem+'.wtedit.json');atomic_json(target,doc)
                atomic_json(target.with_suffix('.meta.json'),{'title':doc.get('title',doc.get('episode',''))})
                return self.json(200,{'ok':True,'path':str(target),'fileName':target.name})
            if path=='/api/handoff':
                revision=body.get('revision')
                if not isinstance(revision,dict):raise ValueError('Revision object required')
                folder=EDITOR/'handoff'/stem
                document_path=folder/'document.wtedit.json';revision_path=folder/'revision.json'
                atomic_json(document_path,doc);atomic_json(revision_path,revision)
                instructions={'document':'document.wtedit.json','revision':'revision.json','preserveStyle':True,'sourceFidelity':True,'originalEpisode':doc.get('episode'),'sourceFilesUnchanged':True,'editPolicy':{'default':'local_edit','preserveSubjectIdentity':True,'preserveComposition':True,'additionalArtworkOnlyWhenRequested':True},'projectContextAttached':bool(doc.get('projectContext')),'note':'User edit proposals are not canon approval. Read the original source, PROMPT.md, baselines and region notes before redrawing. Preserve approved style and identity.'}
                atomic_json(folder/'handoff.json',instructions)
                preview_path=None
                if isinstance(body.get('previewHtml'),str):
                    preview_path=folder/'preview.html'
                    preview_path.write_text(body['previewHtml'],encoding='utf-8')
                (folder/'README_APPLY.md').write_text('# User revision handoff\n\nRead document.wtedit.json and revision.json. Review proposed changes against source and PROMPT.md. Preserve the current project style and approved subject identity. Re-read the current project AGENTS.md, PROMPT.md and settings. Use the embedded projectContext for reference, not as a replacement for newer project instructions. Edit only requested image features or regions; preserve the rest of the original artwork, subject form, face, pose, expression, composition and style. Generate additional art only when explicitly requested. Apply movable lettering and layout edits, then verify the resulting mobile HTML. Do not treat rough boxes as completed artwork. The original episodes remain unchanged.\n',encoding='utf-8')
                index=EDITOR/'handoff'/'latest.json'
                with self.server.save_lock:
                    latest=json.loads(index.read_text(encoding='utf-8')) if index.exists() else {}
                    is_local_project=doc.get('projectContext',{}).get('projectRoot')==str(ROOT) and str(doc.get('baseline',{}).get('manifestPath','')).replace('\\','/').startswith('episodes/'+str(doc.get('episode'))+'/')
                    latest_key=doc.get('episode','draft') if is_local_project else 'document:'+str(doc.get('id',stem))
                    latest[latest_key]={'title':doc.get('title',''),'documentId':doc.get('id'),'documentPath':str(document_path),'revisionPath':str(revision_path),'previewPath':str(preview_path) if preview_path else None,'directory':str(folder),'savedAt':datetime.now(timezone.utc).isoformat()}
                    atomic_json(index,latest)
                return self.json(200,{'ok':True,'path':str(folder),'directory':str(folder),'fileName':stem,'documentPath':str(document_path),'revisionPath':str(revision_path),'previewPath':str(preview_path) if preview_path else None,'paths':[str(document_path),str(revision_path)]})
            self.json(404,{'error':'Unknown write API'})
        except PermissionError as e:self.json(403,{'error':str(e)})
        except (ValueError,TypeError,KeyError) as e:self.json(400,{'error':str(e)})
        except Exception as e:self.json(500,{'error':str(e)})
    def log_message(self,fmt,*args):
        print(datetime.now().isoformat(timespec='seconds'),fmt%args,flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--open',action='store_true');args=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.save_lock=threading.Lock()
    url=f'http://127.0.0.1:{server.server_port}/'
    print('ProjectWT editor: '+url,flush=True)
    if args.open:threading.Timer(.4,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()

