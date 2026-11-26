import { getUser } from '@netlify/identity';
import { and, eq, lt, or } from 'drizzle-orm';
import { getReportDb } from '../../db/index.ts';
import { batches, rows } from '../../db/schema.ts';
import { blobKey, boundedBytes, isSameOrigin, reportsStore, validId } from '../lib/report.mjs';
import { runAudit } from '../lib/run-audit.mjs';

const staleAfter = 16 * 60 * 1000;

export default async function audit(req: Request) {
  if (req.method !== 'POST' || !isSameOrigin(req)) return new Response(null, { status: 403 });
  const user = await getUser();
  if (!user) return new Response(null, { status: 401 });

  const body = await boundedBytes(req, 128);
  let id;
  try { id = body && JSON.parse(body.toString()).id; } catch { id = null; }
  if (!validId(id)) return new Response(null, { status: 400 });

  const db = getReportDb();
  const owned = and(eq(batches.id, id), eq(batches.owner, user.id));
  const [batch] = await db.update(batches).set({ status: 'PROCESSING', startedAt: new Date(), summary: null })
    .where(and(owned, or(eq(batches.status, 'QUEUED'), eq(batches.status, 'FAILED'),
      and(eq(batches.status, 'PROCESSING'), lt(batches.startedAt, new Date(Date.now() - staleAfter))))))
    .returning();
  if (!batch) return new Response(null, { status: 204 });

  try {
    const store = reportsStore();
    const files = Object.fromEntries(await Promise.all(Object.keys(batch.files).map(async (role) => {
      const bytes = await store.get(blobKey(batch, role), { type: 'arrayBuffer' });
      if (!bytes) throw new Error('Missing report input');
      return [role, bytes];
    })));
    const result = await runAudit({
      company: batch.company, stir: batch.stir, year: batch.year, period: batch.period,
      files: batch.files, options: batch.options,
    }, files);
    if (result.error) {
      await db.update(batches).set({ status: 'FAILED', summary: { error: result.error } }).where(owned);
      return new Response(null, { status: 204 });
    }

    await db.delete(rows).where(eq(rows.batchId, id));
    for (const [group, records] of [
      ['items', result.items],
      ['shortages', result.items.filter((item) => Number(item.farq_ortiqcha_soni) > 0)],
      ['marking', result.marking],
      ['discrepancies', result.marking.filter((item) => item.has_discrepancy)],
    ]) {
      for (let offset = 0; offset < records.length; offset += 100) {
        await db.insert(rows).values(records.slice(offset, offset + 100).map((data, index) => ({
          batchId: id, group, position: offset + index,
          searchText: `${data.tovar_id} ${data.tovar_nomi_kirill}`, data,
        })));
      }
    }
    await store.set(blobKey(batch, 'export'), new Blob([result.workbook]));
    await db.update(batches).set({ status: 'COMPLETED', summary: result.summary }).where(owned);
  } catch (error) {
    console.error('Report processing failed', error instanceof Error ? error.name : 'UnknownError');
    await db.update(batches).set({ status: 'FAILED', summary: {
      error: 'Tahlil bajarilmadi. Fayl buzilmaganini va ustun sarlavhalarini tekshiring yoki qayta urinib ko‘ring.',
    } }).where(owned);
  }
  return new Response(null, { status: 204 });
}
