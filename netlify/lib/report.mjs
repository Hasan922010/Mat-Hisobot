import { getStore } from '@netlify/blobs';
import { verifyRequestOrigin } from '@netlify/identity';

export const maxBytes = 10 * 1024 * 1024;
export const validId = (value) => typeof value === 'string' && /^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(value);
export function isSameOrigin(req) {
  try {
    verifyRequestOrigin(req);
    return true;
  } catch {
    return false;
  }
}
export const blobKey = (batch, role) => `${batch.id}/${role}`;
export const reportsStore = () => getStore({ name: 'report-files', consistency: 'strong' });

const filePattern = /\.(xlsx|xls|csv)$/i;
const roles = ['kirim', 'chiqim'];
const text = (value, length) => typeof value === 'string' ? value.trim().slice(0, length) : '';

export function parseBatch(input) {
  const company = text(input?.company, 255);
  const stir = text(input?.stir, 20);
  const year = Number(input?.year);
  const period = text(input?.period, 80) || 'Yillik';
  const fileRoles = input?.mode === 'combined' ? ['combined'] : input?.mode === 'separate' ? roles : [];
  if (!company || !/^\d{9}$/.test(stir) || !Number.isInteger(year) || year < 2000 || year > 2100 || !fileRoles.length) return null;

  const files = {};
  const options = {};
  for (const role of fileRoles) {
    const extension = filePattern.exec(text(input.files?.[role], 512))?.[1]?.toLowerCase();
    if (!extension) return null;
    files[role] = extension;
    if (role === 'combined') continue;
    const option = input.options?.[role];
    const columns = {};
    for (const key of ['tovar_id', 'tovar_nomi', 'summa', `${role}_soni`, `${role}_markirovka`]) {
      const column = text(option?.columns?.[key], 200);
      if (column) columns[key] = column;
    }
    options[role] = { sheet: text(option?.sheet, 31), columns };
  }
  return { company, stir, year, period, files, options };
}

export function validFile(bytes, extension) {
  if (!bytes?.byteLength || bytes.byteLength > maxBytes) return false;
  const signatures = { xlsx: [80, 75, 3, 4], xls: [208, 207, 17, 224] };
  return extension === 'csv' || signatures[extension]?.every((byte, index) => bytes[index] === byte) === true;
}

export async function boundedBytes(req, limit) {
  if (!req.body || Number(req.headers.get('content-length')) > limit) return null;
  const reader = req.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return Buffer.concat(chunks, size);
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
}

export const json = (data, status = 200) => Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
export const problem = (error, status) => json({ error }, status);
