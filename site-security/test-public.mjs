import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {enforceRate, isPublishedFile, reserveUpload, UPLOAD_QUOTA} from './lib/security.mjs';

const sqlite = new DatabaseSync(':memory:');
sqlite.exec(`
  CREATE TABLE security_limits (key TEXT PRIMARY KEY, window_start INTEGER NOT NULL, count INTEGER NOT NULL);
  CREATE TABLE security_events (id TEXT PRIMARY KEY, actor_id TEXT, action TEXT, resource TEXT, status INTEGER, occurred_at INTEGER);
  CREATE TABLE uploads (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, kind TEXT, bytes INTEGER NOT NULL, created_at INTEGER);
  CREATE TABLE works (id TEXT PRIMARY KEY, cover TEXT, deleted INTEGER NOT NULL DEFAULT 0);
  CREATE TABLE chapters (series_id TEXT, content TEXT, deleted INTEGER NOT NULL DEFAULT 0);
`);
const db = {prepare(query) {
  let params = [];
  return {
    bind(...values) { params = values; return this; },
    async first() { return sqlite.prepare(query).get(...params) ?? null; },
    async run() { return sqlite.prepare(query).run(...params); },
  };
}};

try {
  // A file is public only while an active work or chapter references it.
  assert.equal(await isPublishedFile(db, 'sample'), false);
  sqlite.prepare('INSERT INTO works (id,cover) VALUES (?,?)').run('demo', '/files/sample');
  assert.equal(await isPublishedFile(db, 'sample'), true);
  sqlite.prepare('UPDATE works SET deleted=1 WHERE id=?').run('demo');
  assert.equal(await isPublishedFile(db, 'sample'), false);

  // Both reservations see the same remaining space. The SQL write decides.
  sqlite.prepare('INSERT INTO uploads VALUES (?,?,?,?,?)').run('seed', 'alice', 'image', UPLOAD_QUOTA - 8, 1);
  const outcomes = await Promise.allSettled(['a', 'b'].map(id =>
    reserveUpload(db, {id, ownerId:'alice', kind:'image', bytes:8, createdAt:2})
  ));
  assert.equal(outcomes.filter(x => x.status === 'fulfilled').length, 1);
  assert.equal(outcomes.filter(x => x.status === 'rejected' && x.reason.status === 413).length, 1);
  assert.equal(sqlite.prepare('SELECT SUM(bytes) AS total FROM uploads WHERE owner_id=?').get('alice').total, UPLOAD_QUOTA);

  // Rate state is stored per user; a new fixed window resets that user's count.
  await enforceRate(db, 'alice', 'write', 2, 60, 120);
  await enforceRate(db, 'alice', 'write', 2, 60, 121);
  await assert.rejects(enforceRate(db, 'alice', 'write', 2, 60, 122), error => error.status === 429);
  await enforceRate(db, 'bob', 'write', 2, 60, 122);
  await enforceRate(db, 'alice', 'write', 2, 60, 180);

  console.log('Passed: file publication lifecycle, atomic quota reservation, per-user rate window');
} finally {
  sqlite.close();
}
