import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';

const resolve = createRequire(import.meta.url).resolve;
const cdn = 'https://cdn.jsdelivr.net/pyodide/v0.28.3/full/';
const pypi = 'https://files.pythonhosted.org/packages/';
export const pyodidePackages = ['pandas', 'xlrd'];
export const purePackages = [
  ['c0/da/977ded879c29cbd04de313843e76868e6e13408a94ed6b987245dc7c8506/openpyxl-3.1.5-py2.py3-none-any.whl', '5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2'],
  ['07/6c/aa3f2f849e01cb6a001cd8554a88d4c77c5c1a31c95bdf1cf9301e6d9ef4/defusedxml-0.7.1-py2.py3-none-any.whl', 'a352e7e428770286cc899e2542b6cdaedb2b4953ff269a210103ec58f6198a61'],
  ['c1/8b/5fe2cc11fee489817272089c4203e679c63b570a5aaeb18d852ae3cbba6a/et_xmlfile-2.0.0-py3-none-any.whl', '7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa'],
  ['d3/28/9d808fe62375b9aab5ba92fa9b29371297b067c2790b2d7cda648b1e2f8d/rapidfuzz-3.14.3.tar.gz', '2491937177868bc4b1e469087601d53f925e8d270ccc21e07404b4b5814b7b5f'],
];

export const filename = (source) => source.split('/').at(-1);

export async function fetchAuditPackages(directory) {
  await mkdir(directory, { recursive: true });
  const lock = JSON.parse(await readFile(join(dirname(resolve('pyodide')), 'pyodide-lock.json'), 'utf8'));
  const packages = new Map();
  function visit(name) {
    if (packages.has(name)) return;
    const entry = lock.packages[name];
    packages.set(name, [`${cdn}${entry.file_name}`, entry.sha256]);
    entry.depends.forEach(visit);
  }
  pyodidePackages.forEach(visit);

  await Promise.all([...packages.values(), ...purePackages.map(([source, hash]) => [pypi + source, hash])].map(async ([url, hash]) => {
    const path = join(directory, filename(url));
    const matches = (data) => createHash('sha256').update(data).digest('hex') === hash;
    const existing = await readFile(path).catch(() => null);
    if (existing && matches(existing)) return;
    const response = await fetch(url, { signal: AbortSignal.timeout(60000) });
    if (!response.ok) throw new Error(`Failed to download ${filename(url)} (${response.status})`);
    const data = Buffer.from(await response.arrayBuffer());
    if (!matches(data)) throw new Error(`Invalid checksum for ${filename(url)}`);
    await writeFile(path, data);
  }));
}
