import { drizzle } from 'drizzle-orm/netlify-db';
import * as schema from './schema.ts';

let database: ReturnType<typeof drizzle> | undefined;

export function getReportDb() {
  return database ??= drizzle({ schema });
}
