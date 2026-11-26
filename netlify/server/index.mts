import { readFile } from 'node:fs/promises';
import { getUser } from '@netlify/identity';
import { and, desc, eq, ilike, inArray } from 'drizzle-orm';
import { getReportDb } from '../../db/index.ts';
import { batches, rows } from '../../db/schema.ts';
import { blobKey, boundedBytes, isSameOrigin, json, maxBytes, parseBatch, problem, reportsStore, validFile, validId } from '../lib/report.mjs';

const groups = ['items', 'shortages', 'marking', 'discrepancies'];
const pageSize = 50;
const publicFields = {
  id: batches.id, company: batches.company, stir: batches.stir, year: batches.year, period: batches.period,
  status: batches.status, summary: batches.summary, createdAt: batches.createdAt, startedAt: batches.startedAt,
};

async function serve(req: Request) {
  const url = new URL(req.url);
  const [, api, resource, id, action, role, extra] = url.pathname.replace(/\/$/, '').split('/');
  if (api !== 'api' || resource !== 'reports' || extra || (id && !validId(id))) return problem('Sahifa topilmadi.', 404);
  const method = req.method;
  if (method !== 'GET' && !isSameOrigin(req)) return problem('So‘rovga ruxsat berilmadi.', 403);
  const user = await getUser();
  if (!user) return problem('Avval tizimga kiring.', 401);

  const db = getReportDb();
  const owner = eq(batches.owner, user.id);
  if (!id && method === 'GET') {
    const stir = url.searchParams.get('stir');
    const records = await db.select(publicFields).from(batches)
      .where(and(owner, stir ? eq(batches.stir, stir) : undefined)).orderBy(desc(batches.createdAt)).limit(50);
    return json(records);
  }

  if (!id && method === 'POST') {
    const body = await boundedBytes(req, 8192);
    let data;
    try { data = body && parseBatch(JSON.parse(body.toString())); } catch { data = null; }
    if (!data) return problem('Korxona, STIR, yil yoki fayl formatini tekshiring.', 400);
    const drafts = await db.select({ id: batches.id }).from(batches).where(and(owner, inArray(batches.status, ['DRAFT', 'QUEUED', 'PROCESSING']))).limit(5);
    if (drafts.length >= 5) return problem('Avval kutayotgan hisobotlarni yakunlang yoki o‘chiring.', 429);
    const [batch] = await db.insert(batches).values({ ...data, owner: user.id }).returning({ id: batches.id });
    return json(batch, 201);
  }

  if (!id) return problem('Usulga ruxsat berilmadi.', 405);
  const owned = and(owner, eq(batches.id, id));
  const [batch] = await db.select({ ...publicFields, files: batches.files }).from(batches).where(owned);
  if (!batch) return problem('Hisobot topilmadi.', 404);

  if (!action && method === 'GET') {
    const { files, ...record } = batch;
    return json(record);
  }

  if (action === 'files' && role && method === 'PUT') {
    if (batch.status !== 'DRAFT' || !Object.hasOwn(batch.files, role)) return problem('Fayl yuklashga ruxsat yo‘q.', 409);
    const bytes = await boundedBytes(req, maxBytes);
    if (!bytes) return problem('Fayl hajmi 10 MB dan oshmasligi kerak.', 413);
    if (!validFile(bytes, batch.files[role])) return problem('Fayl formati yoki tarkibi noto‘g‘ri.', 400);
    await reportsStore().set(blobKey(batch, role), new Blob([new Uint8Array(bytes)]), { onlyIfNew: true });
    return json({ uploaded: true });
  }

  if (role) return problem('Sahifa topilmadi.', 404);
  if (action === 'queue' && method === 'POST') {
    if (batch.status !== 'DRAFT') return problem('Hisobot allaqachon yuborilgan.', 409);
    const store = reportsStore();
    const files = await Promise.all(Object.keys(batch.files).map((name) => store.getMetadata(blobKey(batch, name))));
    if (files.some((file) => !file)) return problem('Barcha hujjatlar yuklanmagan.', 400);
    const [queued] = await db.update(batches).set({ status: 'QUEUED' })
      .where(and(owned, eq(batches.status, 'DRAFT'))).returning({ id: batches.id });
    return queued ? json(queued) : problem('Hisobot allaqachon yuborilgan.', 409);
  }

  if (action === 'rows' && method === 'GET') {
    if (batch.status !== 'COMPLETED') return problem('Hisobot hali tayyor emas.', 409);
    const group = url.searchParams.get('group') || 'items';
    if (!groups.includes(group)) return problem('Bo‘lim topilmadi.', 404);
    const search = (url.searchParams.get('q') || '').trim().slice(0, 100).replace(/[\\%_]/g, '\\$&');
    const page = Math.max(1, Math.min(10000, Math.trunc(Number(url.searchParams.get('page'))) || 1));
    const matches = await db.select({ data: rows.data }).from(rows)
      .where(and(eq(rows.batchId, id), eq(rows.group, group), search ? ilike(rows.searchText, `%${search}%`) : undefined))
      .orderBy(rows.position).limit(pageSize + 1).offset((page - 1) * pageSize);
    return json({ items: matches.slice(0, pageSize).map((row) => row.data), more: matches.length > pageSize });
  }

  if (action === 'export' && method === 'GET') {
    if (batch.status !== 'COMPLETED') return problem('Hisobot hali tayyor emas.', 409);
    const stream = await reportsStore().get(blobKey(batch, 'export'), { type: 'stream' });
    if (!stream) return problem('Excel fayli topilmadi.', 404);
    return new Response(stream, { headers: {
      'Cache-Control': 'no-store',
      'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'Content-Disposition': `attachment; filename="MatHisobot_${batch.stir}_${batch.year}.xlsx"`,
    } });
  }

  if (!action && method === 'DELETE') {
    const [deleting] = await db.update(batches).set({ status: 'DELETING' })
      .where(and(owned, inArray(batches.status, ['DRAFT', 'QUEUED', 'FAILED', 'COMPLETED', 'DELETING'])))
      .returning({ id: batches.id });
    if (!deleting) return problem('Tahlil yakunlangandan so‘ng hisobotni o‘chirish mumkin.', 409);
    const store = reportsStore();
    await Promise.all([...Object.keys(batch.files), 'export'].map((name) => store.delete(blobKey(batch, name))));
    await db.delete(batches).where(owned);
    return new Response(null, { status: 204, headers: { 'Cache-Control': 'no-store' } });
  }

  return problem('Sahifa topilmadi.', 404);
}

export default async function handler(req: Request, _context: unknown) {
  try {
    const path = new URL(req.url).pathname.replace(/\/$/, '');
    if (req.method === 'GET' && (path === '/accounts/login' ||
      (path.startsWith('/batches/') && validId(path.slice('/batches/'.length))))) {
      const html = await readFile(new URL('../../public/index.html', import.meta.url), 'utf8');
      return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    }
    return await serve(req);
  } catch (error) {
    console.error('Report API request failed', error instanceof Error ? error.name : 'UnknownError');
    return problem('Xizmatda vaqtinchalik xatolik. Qayta urinib ko‘ring.', 500);
  }
}
