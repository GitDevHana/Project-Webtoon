import {sqliteTable,text,integer,index} from 'drizzle-orm/sqlite-core';
export const securityLimits=sqliteTable('security_limits',{
  key:text('key').primaryKey(), windowStart:integer('window_start').notNull(),
  count:integer('count').notNull(),
});
export const securityEvents=sqliteTable('security_events',{
  id:text('id').primaryKey(), actorId:text('actor_id'), action:text('action').notNull(),
  resource:text('resource').notNull(), status:integer('status').notNull(),
  occurredAt:integer('occurred_at').notNull(),
},t=>[index('security_events_time_idx').on(t.occurredAt)]);
