import { index, integer, jsonb, pgTable, primaryKey, text, timestamp, uuid } from 'drizzle-orm/pg-core';

export const batches = pgTable('report_batch', {
  id: uuid().defaultRandom().primaryKey(),
  owner: text().notNull(),
  company: text().notNull(),
  stir: text().notNull(),
  year: integer().notNull(),
  period: text().notNull(),
  files: jsonb().$type<Record<string, string>>().notNull(),
  options: jsonb().$type<Record<string, { sheet: string; columns: Record<string, string> }>>().notNull(),
  status: text().notNull().default('DRAFT'),
  summary: jsonb(),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
  startedAt: timestamp('started_at', { withTimezone: true }),
}, (table) => [index('report_batch_owner_created_idx').on(table.owner, table.createdAt)]);

export const rows = pgTable('report_row', {
  batchId: uuid('batch_id').notNull().references(() => batches.id, { onDelete: 'cascade' }),
  group: text('row_group').notNull(),
  position: integer().notNull(),
  searchText: text('search_text').notNull(),
  data: jsonb().notNull(),
}, (table) => [primaryKey({ columns: [table.batchId, table.group, table.position] })]);
