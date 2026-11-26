import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fetchAuditPackages } from './audit-dependencies.mjs';
import { boundedBytes, isSameOrigin, parseBatch, validFile, validId } from './report.mjs';
import { runAudit } from './run-audit.mjs';

const metadata = { company: 'Namuna', stir: '123456789', year: 2026, period: 'Yillik' };

test('checks inputs, raw body size and same-origin requests', async () => {
  const input = { ...metadata, mode: 'combined', files: { combined: 'hisobot.XLSX' } };
  assert.deepEqual(parseBatch(input), { ...metadata, files: { combined: 'xlsx' }, options: {} });
  assert.equal(parseBatch({ ...input, stir: '123' }), null);
  assert.equal(parseBatch({ ...input, mode: 'separate' }), null);
  assert.equal(validFile(Buffer.from([80, 75, 3, 4]), 'xlsx'), true);
  assert.equal(validFile(Buffer.from('id,name'), 'xlsx'), false);
  assert.equal(validId('00000000-0000-0000-0000-000000000001'), true);
  assert.equal(validId('../export'), false);
  const origin = 'https://example.org';
  const request = new Request(`${origin}/api/reports`, { method: 'POST', headers: { origin }, body: 'abc' });
  assert.equal(isSameOrigin(request), true);
  assert.equal(isSameOrigin(new Request(`${origin}/api/reports`)), false);
  assert.equal(await boundedBytes(request, 2), null);
});

test('runs the original audit and produces a downloadable workbook', { timeout: 120000 }, async () => {
  const directory = await mkdtemp(join(tmpdir(), 'mat-hisobot-test-'));
  try {
    await fetchAuditPackages(directory);
    const combined = Buffer.from('tovar_id,tovar_nomi,bosh_qoldiq,kirim,chiqim,narx\n101,Shakar oq,10,5,20,12000.50\n102,Yog,10,10,8,18500.25\n');
    const result = await runAudit({ ...metadata, files: { combined: 'csv' }, options: {} }, { combined }, directory);
    assert.equal(result.summary.items, 2);
    assert.equal(result.summary.shortages, 1);
    assert.equal(result.summary.shortageValue, '60002.50');
    assert.equal(result.items.find((item) => item.tovar_id === '101').tovar_nomi_kirill, 'Шакар оқ');
    assert.equal(validFile(result.workbook, 'xlsx'), true);
    assert.ok(Buffer.from(result.workbook).includes('xl/worksheets/sheet5.xml'));

    const kirim = Buffer.from('ID,Mahsulot,Soni,Narx\n001,Shakar,5,12000\n');
    const chiqim = Buffer.from('ID,Mahsulot,Soni,Narx\n001,Shakar,7,12000\n');
    const options = {
      kirim: { sheet: '', columns: { tovar_id: 'ID', tovar_nomi: 'Mahsulot', kirim_soni: 'Soni' } },
      chiqim: { sheet: '', columns: { tovar_id: 'ID', tovar_nomi: 'Mahsulot', chiqim_soni: 'Soni' } },
    };
    const separate = await runAudit({ ...metadata, files: { kirim: 'csv', chiqim: 'csv' }, options }, { kirim, chiqim }, directory);
    assert.equal(separate.summary.shortageValue, '24000.00');
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
