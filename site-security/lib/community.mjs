import config from './analytics-config.mjs';
import { identity, authorizeOwner, json, privateHeaders } from './traffic.mjs';
import { studioPage } from './studio-page.mjs';
import {PAGE_HEADERS,enforceRate,audit,reserveUpload,isPublishedFile,safeResource,privateFileHeaders} from './security.mjs';

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const now = () => Math.floor(Date.now()/1000);
const fail = (status, message) => { throw Object.assign(new Error(message), {status}); };
const html = (body, status=200, extra={}) => new Response(body,{status,headers:{...privateHeaders,...PAGE_HEADERS,'Content-Type':'text/html; charset=utf-8',...extra}});
const signIn = path => '/signin-with-chatgpt?return_to='+encodeURIComponent(path);
const toolbar = `<div class="account-bar"><a href="/">컷온</a><span id="account-info">로그인 없이 무료 감상</span><a href="/studio/">작품 업로드</a><a id="account-link" href="${signIn('/studio/')}" target="_top">로그인</a></div><script src="/account.js" defer></script>`;
export const shell = (title,body) => `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)} | 컷온</title><link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/community.css"><script src="/analytics.js" defer></script></head><body>${toolbar}${body}</body></html>`;

async function userFor(request,env){
  const u=identity(request); let admin=false;
  if(u.id && u.email===config.ownerEmail.toLowerCase()) admin=(await authorizeOwner(request,env.DB,config.ownerEmail)).status===200;
  return {...u,admin};
}
async function baseCatalog(request,env){
  const response=await env.ASSETS.fetch(new Request(new URL('/_library/catalog.json',request.url)));
  if(!response.ok)fail(503,'작품 목록을 불러오지 못했습니다.');
  return response.json();
}
export async function catalogFor(request,env){
  const base=await baseCatalog(request,env);
  const [w,c]=await Promise.all([env.DB.prepare('SELECT * FROM works').all(),env.DB.prepare('SELECT * FROM chapters').all()]);
  const map=new Map(base.series.map(s=>[s.id,{...s,ownerId:null,episodes:[...s.episodes]}]));
  for(const r of w.results){
    if(r.deleted){map.delete(r.id);continue;}
    const old=map.get(r.id);
    map.set(r.id,{...old,id:r.id,ownerId:r.owner_id,title:r.title,subtitle:'',synopsis:r.synopsis,cover:r.cover,hero:r.cover,genres:JSON.parse(r.genres),status:'연재 중',episodes:old?.episodes??[]});
  }
  for(const r of c.results){
    const s=map.get(r.series_id); if(!s)continue;
    const old=s.episodes.find(e=>e.number===r.number);
    s.episodes=s.episodes.filter(e=>e.number!==r.number);
    if(!r.deleted)s.episodes.push({...old,number:r.number,title:r.title,url:`/read/${s.id}/${r.number}/`,thumbnail:old?.thumbnail||s.cover,revision:String(r.updated_at),custom:!!r.content});
  }
  for(const s of map.values()){s.episodes.sort((a,b)=>a.number-b.number);s.latest=s.episodes.at(-1)?.number??0;}
  return {...base,series:[...map.values()]};
}
function publicCatalog(data){return {...data,series:data.series.map(({ownerId,...s})=>s)};}
function textField(body,key,max,required=true){const v=body[key];if(typeof v!=='string'||v.length>max||(required&&!v.trim()))fail(400,`${key} 입력을 확인해 주세요.`);return v.trim();}
async function boundedBytes(request,limit){
  if(Number(request.headers.get('content-length')||0)>limit)fail(413,'파일 크기 제한을 초과했습니다.');
  const reader=request.body?.getReader();if(!reader)fail(400,'내용이 없습니다.');
  const chunks=[];let size=0;
  while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>limit){await reader.cancel();fail(413,'파일 크기 제한을 초과했습니다.');}chunks.push(value);}
  const out=new Uint8Array(size);let at=0;for(const c of chunks){out.set(c,at);at+=c.length;}return out;
}
async function bodyJSON(request){try{const data=JSON.parse(new TextDecoder().decode(await boundedBytes(request,128*1024)));if(!data||typeof data!=='object'||Array.isArray(data))fail(400,'입력 형식을 확인해 주세요.');return data;}catch(e){if(e.status)throw e;fail(400,'입력 형식을 확인해 주세요.');}}
async function mustOwn(request,env,user,id){
  const catalog=await catalogFor(request,env),s=catalog.series.find(s=>s.id===id);
  if(!s)fail(404,'작품을 찾을 수 없습니다.');
  if(!user.admin&&s.ownerId!==user.id)fail(403,'본인의 작품만 관리할 수 있습니다.');
  return s;
}
async function validateFile(env,user,id,kind){
  if(!/^[a-f0-9-]{36}$/.test(id))fail(400,'업로드한 파일을 선택해 주세요.');
  const row=await env.DB.prepare('SELECT * FROM uploads WHERE id=?').bind(id).first();
  if(!row||(!user.admin&&row.owner_id!==user.id)||(kind&&row.kind!==kind))fail(400,'사용할 수 없는 파일입니다.');
  return row;
}
async function workValues(env,user,body){
  const title=textField(body,'title',150),synopsis=textField(body,'synopsis',5000,false);
  let cover='';
  if(body.cover){
    if(typeof body.cover!=='string')fail(400,'표지를 확인해 주세요.');
    if(body.cover.startsWith('/files/')){await validateFile(env,user,body.cover.slice(7),'image');cover=body.cover;}
    else if(user.admin&&/^\/media\/[a-f0-9]+\.(jpg|png|webp)$/.test(body.cover))cover=body.cover;
    else fail(400,'표지를 먼저 업로드해 주세요.');
  }
  if(!Array.isArray(body.genres)||body.genres.length>5||body.genres.some(g=>typeof g!=='string'||g.length>30))fail(400,'장르는 5개까지 입력할 수 있습니다.');
  return {title,synopsis,cover,genres:JSON.stringify(body.genres)};
}
async function api(request,env,path,user){
  if(path==='/api/session'&&request.method==='GET')return json({signedIn:!!user.id,admin:user.admin,signIn:signIn('/studio/'),signOut:'/signout-with-chatgpt?return_to=%2F'});
  if(path==='/api/security-events'&&request.method==='GET'){
    if(!user.id)fail(401,'로그인이 필요합니다.');if(!user.admin)fail(403,'관리자만 확인할 수 있습니다.');
    const events=await env.DB.prepare('SELECT id,actor_id,action,resource,status,occurred_at FROM security_events WHERE occurred_at>=? ORDER BY occurred_at DESC LIMIT 100').bind(now()-30*86400).all();
    return json({events:events.results,retentionDays:30});
  }
  if(path==='/api/works'&&request.method==='GET'){
    if(!user.id)fail(401,'로그인이 필요합니다.');
    const catalog=await catalogFor(request,env);return json({series:catalog.series.filter(s=>user.admin||s.ownerId===user.id),admin:user.admin});
  }
  if(path==='/api/uploads'&&request.method==='GET'){
    if(!user.id)fail(401,'로그인이 필요합니다.');
    const rows=await env.DB.prepare('SELECT id,kind,bytes,created_at FROM uploads WHERE owner_id=? ORDER BY created_at DESC LIMIT 100').bind(user.id).all();
    const uploads=[];for(const row of rows.results)uploads.push({...row,published:await isPublishedFile(env.DB,row.id)});
    return json({uploads,limit:100});
  }
  if(!['POST','PUT','PATCH','DELETE'].includes(request.method))fail(405,'허용되지 않은 요청입니다.');
  if(!user.id||!user.email)fail(401,'로그인 후 업로드할 수 있습니다.');
  if(request.headers.get('origin')!==new URL(request.url).origin)fail(403,'같은 사이트에서 요청해 주세요.');
  await enforceRate(env.DB,user.id,'write',180,60);
  if(path==='/api/uploads'&&request.method==='POST'){
    await enforceRate(env.DB,user.id,'upload',120,600);
    if(!env.BUCKET)fail(503,'업로드 저장소를 준비하고 있습니다.');
    const kind=request.headers.get('x-file-kind');
    if(!['image','html'].includes(kind))fail(400,'이미지 또는 HTML 파일을 선택해 주세요.');
    const bytes=await boundedBytes(request,kind==='html'?32*1024*1024:20*1024*1024);
    let mime='text/html; charset=utf-8';
    if(kind==='image'){
      if(bytes[0]===0x89&&new TextDecoder().decode(bytes.slice(1,4))==='PNG')mime='image/png';
      else if(bytes[0]===255&&bytes[1]===216&&bytes[2]===255)mime='image/jpeg';
      else if(new TextDecoder().decode(bytes.slice(0,4))==='RIFF'&&new TextDecoder().decode(bytes.slice(8,12))==='WEBP')mime='image/webp';
      else fail(400,'PNG, JPG, WebP 이미지만 업로드할 수 있습니다.');
    }else if(!/<(?:html|svg|main|body|div|section)\b/i.test(new TextDecoder().decode(bytes.slice(0,8192))))fail(400,'HTML 웹툰 파일인지 확인해 주세요.');
    const id=crypto.randomUUID();
    await reserveUpload(env.DB,{id,ownerId:user.id,kind,bytes:bytes.length,createdAt:now(),admin:user.admin});
    try{await env.BUCKET.put(id,bytes,{httpMetadata:{contentType:mime}});}
    catch(e){await env.DB.prepare('DELETE FROM uploads WHERE id=?').bind(id).run();throw e;}
    return json({id,url:'/files/'+id,kind},201);
  }
  const uploadMatch=/^\/api\/uploads\/([a-f0-9-]{36})$/.exec(path);
  if(uploadMatch&&request.method==='DELETE'){
    const id=uploadMatch[1];await validateFile(env,user,id);
    if(await isPublishedFile(env.DB,id))fail(409,'게시 중인 파일은 회차 또는 표지에서 먼저 제외해 주세요.');
    await env.BUCKET.delete(id);await env.DB.prepare('DELETE FROM uploads WHERE id=?').bind(id).run();return json({ok:true});
  }
  if(path==='/api/works'&&request.method==='POST'){
    const body=await bodyJSON(request),v=await workValues(env,user,body),id='work-'+crypto.randomUUID();
    await env.DB.prepare('INSERT INTO works (id,owner_id,title,synopsis,cover,genres,deleted,updated_at) VALUES (?,?,?,?,?,?,0,?)').bind(id,user.id,v.title,v.synopsis,v.cover,v.genres,now()).run();
    return json({id},201);
  }
  const match=/^\/api\/works\/([a-z][a-z0-9-]{0,79})(?:\/chapters\/([1-9]\d{0,3}))?$/.exec(path);
  if(!match)fail(404,'주소를 확인해 주세요.');
  const [,id,num]=match,s=await mustOwn(request,env,user,id),owner=s.ownerId||user.id;
  if(!num){
    if(request.method==='DELETE'){
      await env.DB.prepare('INSERT INTO works (id,owner_id,title,synopsis,cover,genres,deleted,updated_at) VALUES (?,?,?,?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET deleted=1,updated_at=excluded.updated_at').bind(id,owner,s.title,s.synopsis,s.cover,JSON.stringify(s.genres),now()).run();
      return json({ok:true});
    }
    if(request.method!=='PATCH')fail(405,'허용되지 않은 요청입니다.');
    const v=await workValues(env,user,await bodyJSON(request));
    await env.DB.prepare('INSERT INTO works (id,owner_id,title,synopsis,cover,genres,deleted,updated_at) VALUES (?,?,?,?,?,?,0,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,synopsis=excluded.synopsis,cover=excluded.cover,genres=excluded.genres,updated_at=excluded.updated_at').bind(id,owner,v.title,v.synopsis,v.cover,v.genres,now()).run();
    return json({ok:true});
  }
  const number=Number(num),key=id+':'+number;
  if(request.method==='DELETE'){
    if(!s.episodes.some(e=>e.number===number))fail(404,'회차를 찾을 수 없습니다.');
    await env.DB.prepare('INSERT INTO chapters (id,series_id,number,title,content,deleted,updated_at) VALUES (?,?,?,?,NULL,1,?) ON CONFLICT(id) DO UPDATE SET deleted=1,updated_at=excluded.updated_at').bind(key,id,number,'',now()).run();return json({ok:true});
  }
  if(request.method!=='PUT')fail(405,'허용되지 않은 요청입니다.');
  const body=await bodyJSON(request),title=textField(body,'title',150);
  let content=null;
  if(body.content){
    if(body.content.kind==='html'){await validateFile(env,user,body.content.file,'html');content={kind:'html',file:body.content.file};}
    else if(body.content.kind==='images'&&Array.isArray(body.content.files)&&body.content.files.length>0&&body.content.files.length<=100){for(const id of body.content.files)await validateFile(env,user,id,'image');content={kind:'images',files:body.content.files};}
    else fail(400,'원고 파일을 확인해 주세요.');
  }else if(!s.episodes.some(e=>e.number===number))fail(400,'새 회차에는 원고 파일이 필요합니다.');
  await env.DB.prepare('INSERT INTO chapters (id,series_id,number,title,content,deleted,updated_at) VALUES (?,?,?,?,?,0,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,content=COALESCE(excluded.content,chapters.content),deleted=0,updated_at=excluded.updated_at').bind(key,id,number,title,content?JSON.stringify(content):null,now()).run();
  return json({ok:true,url:`/read/${id}/${number}/`});
}
function card(s){return `<article class="series-card"><a class="cover" href="/series/${s.id}/">${s.cover?`<img src="${esc(s.cover)}" alt="${esc(s.title)}" loading="lazy">`:'<span class="cover-placeholder">새로운 이야기</span>'}<span class="cover-count">${s.episodes.length}화</span></a><div class="card-title"><a href="/series/${s.id}/">${esc(s.title)}</a><button class="save" data-save="${s.id}" aria-pressed="false" aria-label="관심 작품">♡</button></div><p>${s.genres.map(esc).join(' · ')}</p></article>`;}
function home(data){
  const first=data.series[0];
  const hero=first?`<section class="hero" id="home-hero"><div class="hero-copy"><p class="eyebrow">CUTON · 다음 장면이 기다려지는 곳</p><span class="genre-pill">${first.genres.map(esc).join(' · ')}</span><h1>${esc(first.title)}</h1><p class="hero-desc">${esc(first.subtitle||first.synopsis)}</p><a class="button" href="/series/${first.id}/">이야기 만나기 →</a></div><div class="hero-art">${first.hero?`<img src="${esc(first.hero)}" alt="">`:''}</div></section>`:'';
  return shell('웹툰 서재',`<header class="header"><a class="logo" href="/">컷온</a><nav><a href="/" data-tab="all">전체 작품</a><a href="/?shelf" data-tab="shelf">내 서재</a></nav><div class="search"><input id="search" aria-label="작품 검색" placeholder="작품 제목 검색"></div></header><main class="container">${hero}<section class="library"><div class="section-title"><h2 id="library-title">전체 작품 <span>${data.series.length}</span></h2><a href="/studio/">내 작품 올리기 ↗</a></div><div class="cards">${data.series.map(s=>`<div class="series-card-filter" data-id="${s.id}" data-title="${esc(s.title)}" data-genres="${esc(s.genres.join(' '))}">${card(s)}</div>`).join('')}</div><div id="empty" hidden>작품이 없습니다.</div></section><div id="continue" class="continue" hidden></div></main><script src="/library.js" defer></script>`);
}
function seriesPage(s){return shell(s.title,`<main class="container"><a class="back" href="/">← 전체 작품</a><section class="series-hero"><div class="detail-cover">${s.cover?`<img src="${esc(s.cover)}" alt="${esc(s.title)}">`:''}</div><div class="series-copy"><div class="tags">${s.genres.map(g=>`<span>${esc(g)}</span>`).join('')}</div><h1>${esc(s.title)}</h1><p class="status">연재 중 · 총 ${s.episodes.length}화</p><p class="synopsis">${esc(s.synopsis)}</p>${s.episodes.length?`<a class="button" href="${s.episodes[0].url}">첫화부터 보기 →</a>`:'<p>첫 회차를 준비하고 있습니다.</p>'}<a class="outline" href="/studio/?work=${s.id}">작품 관리</a></div></section><section class="episode-list"><h2>전체 회차</h2>${[...s.episodes].reverse().map(e=>`<a class="episode-row" href="${e.url}"><div class="ep-thumb">${e.thumbnail?`<img src="${esc(e.thumbnail)}" alt="" loading="lazy">`:''}</div><div class="ep-info"><strong>${e.number}화 <span>${esc(e.title)}</span></strong><p>무료로 감상하기</p></div><span class="ep-arrow">↗</span></a>`).join('')}</section></main>`);}
function readerNav(s,e){const index=s.episodes.findIndex(x=>x.number===e.number);return `<nav class="co-readerfoot">${index>0?`<a href="${s.episodes[index-1].url}">← 이전화</a>`:'<span>첫화</span>'}<a href="/series/${s.id}/">회차 목록</a>${index<s.episodes.length-1?`<a href="${s.episodes[index+1].url}">다음화 →</a>`:'<span>마지막 회차</span>'}</nav>`;}

export async function handleCommunity(request,env){
  const url=new URL(request.url),path=url.pathname.replace(/\/index\.html$/, '/');
  const isApi=/^\/api\/(session|security-events|works(?:\/|$)|uploads(?:\/|$))/.test(path);
  const routed=isApi||path==='/'||path==='/catalog.json'||/^\/studio\/?$/.test(path)||path.startsWith('/series/')||path.startsWith('/read/')||path.startsWith('/files/');
  if(!routed)return null;
  try{
    if(path.startsWith('/files/')){
      if(!['GET','HEAD'].includes(request.method))fail(405,'허용되지 않은 요청입니다.');
      const id=path.slice(7);if(!/^[a-f0-9-]{36}$/.test(id))fail(404,'파일을 찾을 수 없습니다.');
      if(!env.DB)fail(503,'파일 저장소를 준비하고 있습니다.');
      const record=await env.DB.prepare('SELECT owner_id FROM uploads WHERE id=?').bind(id).first();
      if(!record)fail(404,'파일을 찾을 수 없습니다.');
      if(!await isPublishedFile(env.DB,id)){
        const u=identity(request);
        if(!u.id||(u.id!==record.owner_id&&!(await userFor(request,env)).admin))fail(404,'파일을 찾을 수 없습니다.');
      }
      const object=await env.BUCKET?.get(id);if(!object)fail(404,'파일을 찾을 수 없습니다.');
      return new Response(request.method==='HEAD'?null:object.body,{headers:privateFileHeaders(object.httpMetadata.contentType)});
    }
    if(!env.DB)fail(503,'작품 저장소를 준비하고 있습니다.');
    if(isApi){
      const user=await userFor(request,env),writing=['POST','PUT','PATCH','DELETE'].includes(request.method);
      let response,error;
      try{response=await api(request,env,path,user);}catch(e){error=e;}
      if(writing&&user.id&&error?.status!==429){
        try{await audit(env.DB,{actorId:user.id,action:'write.'+request.method,resource:safeResource(path),status:error?(error.status||503):response.status});}
        catch(e){if(e.status!==429)console.warn('security_audit_write_failed');}
      }
      if(error)throw error;return response;
    }
    if(!['GET','HEAD'].includes(request.method))fail(405,'허용되지 않은 요청입니다.');
    if(/^\/studio\/?$/.test(path)){
      const user=await userFor(request,env);
      return html(shell('작품 관리',user.id?studioPage:`<main class="studio"><h1>당신의 이야기를 올려 주세요.</h1><p>감상은 로그인 없이, 작품 업로드와 관리는 로그인 후 이용할 수 있습니다.</p><a class="button" href="${signIn('/studio/')}" target="_top">ChatGPT로 로그인</a></main>`));
    }
    const data=await catalogFor(request,env);
    if(path==='/catalog.json')return json(publicCatalog(data));
    if(path==='/')return html(home(data));
    const m=/^\/(series|read)\/([a-z][a-z0-9-]{0,79})(?:\/([1-9]\d{0,3}))?\/?$/.exec(path);
    if(!m)fail(404,'주소를 확인해 주세요.');
    const s=data.series.find(s=>s.id===m[2]);if(!s)fail(404,'작품을 찾을 수 없습니다.');
    if(m[1]==='series')return html(seriesPage(s));
    const e=s.episodes.find(e=>e.number===Number(m[3]));if(!e)fail(404,'게시되지 않은 회차입니다.');
    const chapter=await env.DB.prepare('SELECT content FROM chapters WHERE id=? AND deleted=0').bind(s.id+':'+e.number).first();
    if(chapter?.content){
      const content=JSON.parse(chapter.content);
      return html(shell(e.title,`<div class="reader-title">${esc(s.title)} · ${e.number}화 · ${esc(e.title)}</div>${content.kind==='html'?`<iframe class="manuscript" title="${esc(e.title)}" sandbox src="/files/${content.file}"></iframe>`:`<main class="image-reader">${content.files.map(id=>`<img src="/files/${id}" alt="" loading="lazy">`).join('')}</main>`}${readerNav(s,e)}`));
    }
    const asset=await env.ASSETS.fetch(new Request(new URL(`/_library/${s.id}/${e.number}.txt`,url)));
    if(!asset.ok)fail(404,'원고를 찾을 수 없습니다.');
    return new HTMLRewriter().on('head',{element(el){el.append('<link rel="stylesheet" href="/community.css">',{html:true});}}).on('body',{element(el){el.prepend(toolbar,{html:true});}}).on('.co-readerbar span',{element(el){el.setInnerContent(`${e.number}화 · ${esc(e.title)}`,{html:true});}}).on('.co-readerfoot',{element(el){el.replace(readerNav(s,e),{html:true});}}).transform(new Response(asset.body,{headers:{...privateHeaders,...PAGE_HEADERS,'Content-Type':'text/html; charset=utf-8'}}));
  }catch(e){const response=isApi?json({error:e.status?e.message:'저장소 연결에 문제가 있습니다. 잠시 후 다시 시도해 주세요.'},e.status||503):html(shell('안내',`<main class="studio"><h1>${esc(e.status?e.message:'잠시 후 다시 시도해 주세요.')}</h1><a href="/">작품 목록으로</a></main>`),e.status||503);if(e.retryAfter)response.headers.set('Retry-After',String(e.retryAfter));return response;}
}
