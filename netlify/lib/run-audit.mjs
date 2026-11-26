import { access, readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { loadPyodide } from 'pyodide';
import { filename, purePackages, pyodidePackages } from './audit-dependencies.mjs';

const sourcePaths = [
  'reports/__init__.py', 'reports/services/__init__.py', 'reports/services/audit_engine.py',
  'reports/services/fuzzy_matcher.py', 'reports/services/transliterator.py', 'reports/services/marking_engine.py',
  'reports/services/excel_builder.py', 'reports/services/ai_advisor.py', 'netlify/lib/audit_bridge.py',
];

async function findRoot() {
  const roots = [process.cwd(), import.meta.dirname, resolve(import.meta.dirname, '../..')];
  for (const root of roots) {
    if (await access(join(root, sourcePaths.at(-1))).then(() => true, () => false)) return root;
  }
  throw new Error('Audit sources are missing from the function bundle');
}

export async function runAudit(batch, files, packageDirectory) {
  const root = await findRoot();
  const directory = packageDirectory || join(root, 'netlify/lib/audit-packages');
  const py = await loadPyodide({ packageCacheDir: directory, stdout: () => {}, stderr: () => {} });
  await py.loadPackage(pyodidePackages, { messageCallback: () => {} });
  await py.loadPackage(purePackages.filter(([source]) => source.endsWith('.whl')).map(([source]) => join(directory, filename(source))), { messageCallback: () => {} });

  py.FS.mkdir('/audit');
  py.FS.mkdirTree('/audit/reports/services');
  const rapidfuzz = filename(purePackages.find(([source]) => source.endsWith('.tar.gz'))[0]);
  py.FS.writeFile('/audit/rapidfuzz.tar.gz', await readFile(join(directory, rapidfuzz)));
  py.runPython(`
import os, sys, tarfile
from pathlib import Path

sys.path.insert(0, "/audit")
os.environ["RAPIDFUZZ_IMPLEMENTATION"] = "python"
with tarfile.open("/audit/rapidfuzz.tar.gz", "r:gz") as archive:
    for member in archive.getmembers():
        parts = Path(member.name).parts
        if member.isfile() and len(parts) >= 4 and parts[1:3] == ("src", "rapidfuzz") and member.name.endswith(".py") and ".." not in parts:
            destination = Path("/audit").joinpath(*parts[2:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.extractfile(member).read())
`);

  await Promise.all(sourcePaths.map(async (source) => {
    const path = source.startsWith('reports/') ? source : 'audit_bridge.py';
    py.FS.writeFile(`/audit/${path}`, await readFile(join(root, source)));
  }));
  for (const [role, extension] of Object.entries(batch.files)) {
    py.FS.writeFile(`/audit/${role}.${extension}`, new Uint8Array(files[role]));
  }
  py.globals.set('batch_json', JSON.stringify(batch));
  const result = JSON.parse(py.runPython('from audit_bridge import audit_json; audit_json(batch_json)'));
  if (result.error) return result;
  return { ...result, workbook: py.FS.readFile('/audit/export.xlsx') };
}
