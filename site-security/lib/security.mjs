import {privateHeaders} from './traffic.mjs';
export const UPLOAD_QUOTA=500*1024*1024;
export const PAGE_HEADERS={
  'Referrer-Policy':'same-origin',
  'X-Content-Type-Options':'nosniff',
  'Permissions-Policy':'camera=(), microphone=(), geolocation=(), payment=()',
  'Content-Security-Policy':"frame-ancestors 'self' https://chatgpt.com https://*.chatgpt.com; base-uri 'self'; object-src 'none'; form-action 'self'",
};
export function securityFailure(status,message,retryAfter){
  const e=Object.assign(new Error(message),{status});if(retryAfter)e.retryAfter=retryAfter;throw e;
}
// One atomic UPSERT per account/window. Isolate-local Maps are not global limits.
export async function enforceRate(db,userId,scope,limit,seconds,time=Math.floor(Date.now()/1000)){
  const window=Math.floor(time/seconds)*seconds;
  const row=await db.prepare(`INSERT INTO security_limits (key,window_start,count) VALUES (?,?,1)
    ON CONFLICT(key) DO UPDATE SET window_start=excluded.window_start,
    count=CASE WHEN security_limits.window_start=excluded.window_start THEN security_limits.count+1 ELSE 1 END
    RETURNING count`).bind(scope+':'+userId,window).first();
  if(row.count>limit)securityFailure(429,'요청이 많습니다. 잠시 후 다시 시도해 주세요.',window+seconds-time);
}
// This stores a pseudonymous Site ID, fixed event type/resource ID and status only.
// Never pass request headers, email, cookies, tokens, filenames or manuscript text.
export async function audit(db,{actorId=null,action,resource,status},time=Math.floor(Date.now()/1000)){
  if(actorId)await enforceRate(db,actorId,'audit',120,60,time);
  await db.prepare('INSERT INTO security_events (id,actor_id,action,resource,status,occurred_at) VALUES (?,?,?,?,?,?)')
    .bind(crypto.randomUUID(),actorId,action,resource,status,time).run();
  // Retention is bounded to 30 days; expired limiter windows need no history.
  await db.prepare('DELETE FROM security_events WHERE occurred_at<?').bind(time-30*86400).run();
  await db.prepare('DELETE FROM security_limits WHERE window_start<?').bind(time-86400).run();
}
export async function reserveUpload(db,{id,ownerId,kind,bytes,createdAt,admin=false}){
  // The quota comparison and insertion run in the same SQLite write statement.
  // Upload rows include in-flight reservations; concurrent requests cannot both
  // spend the same free space. A failed R2 write releases its reservation.
  const row=await db.prepare(`INSERT INTO uploads (id,owner_id,kind,bytes,created_at)
    SELECT ?,?,?,?,? WHERE ?=1 OR
    (SELECT COALESCE(SUM(bytes),0) FROM uploads WHERE owner_id=?)+?<=?
    RETURNING id`).bind(id,ownerId,kind,bytes,createdAt,admin?1:0,ownerId,bytes,UPLOAD_QUOTA).first();
  if(!row)securityFailure(413,'계정 저장 공간 500MB를 초과했습니다.');
}
export async function isPublishedFile(db,id){
  const row=await db.prepare(`SELECT 1 AS allowed FROM works WHERE deleted=0 AND cover=?
    UNION ALL SELECT 1 AS allowed FROM chapters c LEFT JOIN works w ON w.id=c.series_id
    WHERE c.deleted=0 AND COALESCE(w.deleted,0)=0 AND c.content IS NOT NULL AND
    (json_extract(c.content,'$.file')=? OR EXISTS (SELECT 1 FROM json_each(c.content,'$.files') j WHERE j.value=?)) LIMIT 1`)
    .bind('/files/'+id,id,id).first();
  return !!row;
}
export function safeResource(path){
  const work=/^\/api\/works\/([a-z][a-z0-9-]{0,79})(?:\/chapters\/([1-9]\d{0,3}))?$/.exec(path);
  if(work)return work[1]+(work[2]?':'+work[2]:'');
  return ['/api/uploads','/api/works'].includes(path)?path:'api';
}
export function privateFileHeaders(contentType){return {...privateHeaders,'Content-Type':contentType,
  'Content-Security-Policy':"sandbox; default-src 'none'; img-src data: blob: 'self'; style-src 'unsafe-inline'; font-src data:; script-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'",
  'Referrer-Policy':'no-referrer'};}
