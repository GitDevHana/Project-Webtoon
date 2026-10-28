const DAY = 86400, SESSION = 1800;
const UUID = /^[a-f\d]{8}-[a-f\d]{4}-4[a-f\d]{3}-[89ab][a-f\d]{3}-[a-f\d]{12}$/i;
const privateHeaders = {'Cache-Control':'private, no-store, max-age=0','Vary':'Cookie, oai-authenticated-user-id','X-Robots-Tag':'noindex, nofollow','X-Content-Type-Options':'nosniff'};
export const json = (body,status=200) => new Response(JSON.stringify(body),{status,headers:{...privateHeaders,'Content-Type':'application/json; charset=utf-8'}});
export function koreanDay(seconds){return new Date((seconds+9*3600)*1000).toISOString().slice(0,10);}
export function identity(request){return {id:request.headers.get('oai-authenticated-user-id')||'',email:(request.headers.get('oai-authenticated-user-email')||'').toLowerCase()};}
export async function authorizeOwner(request,db,ownerEmail){
 const user=identity(request);
 if(!user.id || !user.email)return {status:401};
 if(user.email!==ownerEmail.toLowerCase())return {status:403};
 if(!db)return {status:503};
 // Bootstrap only from the configured verified Sites identity, then pin the
 // stable Site-scoped ID. A first anonymous visitor cannot claim ownership.
 await db.prepare('INSERT OR IGNORE INTO analytics_owner (singleton,user_id) VALUES (1,?)').bind(user.id).run();
 const pinned=await db.prepare('SELECT user_id FROM analytics_owner WHERE singleton=1').first();
 return {status:pinned?.user_id===user.id?200:403};
}
function pathInfo(path,episodes){
 if(path==='/' || path==='/series/another-world/')return {page:path,episode:null};
 const m=/^\/read\/another-world\/([1-9]\d{0,2})\/$/.exec(path);
 return m && episodes.includes(Number(m[1]))?{page:path,episode:Number(m[1])}:null;
}
async function smallJSON(request){
 if(Number(request.headers.get('content-length')||0)>4096)throw Error('large');
 const reader=request.body?.getReader();if(!reader)throw Error('missing');
 let size=0;const chunks=[];
 while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>4096){await reader.cancel();throw Error('large');}chunks.push(value);}
 const bytes=new Uint8Array(size);let at=0;for(const c of chunks){bytes.set(c,at);at+=c.length;}
 return JSON.parse(new TextDecoder().decode(bytes));
}
export async function collect(request,db,config,now=Math.floor(Date.now()/1000)){
 if(request.method!=='POST')return json({error:'허용되지 않은 요청입니다.'},405);
 const url=new URL(request.url);
 if(request.headers.get('origin')!==url.origin)return json({error:'허용되지 않은 요청입니다.'},403);
 if(identity(request).id && identity(request).email===config.ownerEmail.toLowerCase())return new Response(null,{status:204,headers:privateHeaders});
 if(request.headers.get('DNT')==='1' || /bot|crawler|spider|preview|headless/i.test(request.headers.get('user-agent')||''))return new Response(null,{status:204,headers:privateHeaders});
 let body;try{body=await smallJSON(request);}catch{return json({error:'올바르지 않은 요청입니다.'},400);}
 if(!body || typeof body!=='object' || Array.isArray(body) || ['visitorId','eventId','path'].some(k=>typeof body[k]!=='string'))return json({error:'올바르지 않은 요청입니다.'},400);
 const info=pathInfo(body.path,config.episodes);
 if(!UUID.test(body.visitorId||'') || !UUID.test(body.eventId||'') || !info)return json({error:'올바르지 않은 요청입니다.'},400);
 if(!db)return json({error:'집계 준비 중입니다.'},503);
 const visitorKey=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(body.visitorId)))).map(x=>x.toString(16).padStart(2,'0')).join('');
 await db.batch([
  db.prepare('INSERT INTO analytics_visitors (visitor_key,session_start,last_seen) VALUES (?,?,?) ON CONFLICT(visitor_key) DO UPDATE SET session_start=CASE WHEN excluded.last_seen-analytics_visitors.last_seen>=? THEN excluded.session_start ELSE analytics_visitors.session_start END,last_seen=MAX(analytics_visitors.last_seen,excluded.last_seen)').bind(visitorKey,now,now,SESSION),
  db.prepare('INSERT OR IGNORE INTO analytics_events (event_id,visitor_key,page,episode,occurred_at,day_kr,session_start) SELECT ?,visitor_key,?,?,?,?,session_start FROM analytics_visitors WHERE visitor_key=? AND NOT EXISTS (SELECT 1 FROM analytics_events WHERE visitor_key=? AND page=? AND occurred_at>?)').bind(body.eventId,info.page,info.episode,now,koreanDay(now),visitorKey,visitorKey,info.page,now-10)
 ]);
 return new Response(null,{status:204,headers:privateHeaders});
}
export async function stats(db,period,now=Math.floor(Date.now()/1000)){
 const periods={today:1,week:7,month:30,all:null};if(!(period in periods))return json({error:'조회 기간을 확인해 주세요.'},400);
 const from=periods[period]===null?'0000-01-01':koreanDay(now-(periods[period]-1)*DAY);
 const totals=db.prepare("SELECT COUNT(*) AS pageviews,COUNT(DISTINCT visitor_key) AS visitors,COUNT(DISTINCT visitor_key||':'||session_start) AS visits,COALESCE(SUM(CASE WHEN episode IS NOT NULL THEN 1 ELSE 0 END),0) AS episodeViews FROM analytics_events WHERE day_kr>=?").bind(from).first();
 const [summary,today,lifetime,episodes,days]=await Promise.all([
  totals,db.prepare('SELECT COUNT(*) AS pageviews,COUNT(DISTINCT visitor_key) AS visitors FROM analytics_events WHERE day_kr=?').bind(koreanDay(now)).first(),
  db.prepare('SELECT COUNT(*) AS pageviews,MIN(occurred_at) AS firstEvent FROM analytics_events').first(),
  db.prepare('SELECT episode,COUNT(*) AS views,COUNT(DISTINCT visitor_key) AS visitors FROM analytics_events WHERE day_kr>=? AND episode IS NOT NULL GROUP BY episode ORDER BY episode DESC').bind(from).all(),
  db.prepare("SELECT day_kr AS day,COUNT(*) AS pageviews,COUNT(DISTINCT visitor_key) AS visitors,COUNT(DISTINCT visitor_key||':'||session_start) AS visits FROM analytics_events WHERE day_kr>=? GROUP BY day_kr ORDER BY day_kr DESC LIMIT 30").bind(from).all()
 ]);
 return json({period,from,today,summary,lifetime,episodes:episodes.results,days:days.results,asOf:now,timeZone:'Asia/Seoul'});
}
export function accessPage(status){
 const title=status===401?'관리자 로그인이 필요합니다.':status===403?'접근할 수 없습니다.':'통계 연결을 준비하고 있습니다.';
 const text=status===401?'이 사이트를 관리하는 ChatGPT 계정으로 로그인해 주세요.':status===403?'이 통계는 사이트 관리자만 확인할 수 있습니다.':'잠시 후 다시 확인해 주세요. 집계 오류를 조회수 0으로 표시하지 않습니다.';
 return new Response(`<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>컷온 관리자 통계</title><style>body{font:17px/1.7 system-ui;background:#f7f7f3;color:#24352d;margin:0;padding:12vh 8vw}main{max-width:560px;margin:auto}h1{font-size:28px}a{color:#176b4a}p{color:#5c685f}</style><main><h1>${title}</h1><p>${text}</p>${status===401?'<a href="/signin-with-chatgpt?return_to=%2Fadmin%2Fstats%2F" target="_top">ChatGPT로 로그인</a>':'<a href="/">웹툰으로 돌아가기</a>'}</main></html>`,{status,headers:{...privateHeaders,'Content-Type':'text/html; charset=utf-8'}});
}
export {privateHeaders};
