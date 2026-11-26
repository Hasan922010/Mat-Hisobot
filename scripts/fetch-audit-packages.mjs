import { fileURLToPath } from 'node:url';
import { fetchAuditPackages } from '../netlify/lib/audit-dependencies.mjs';

await fetchAuditPackages(fileURLToPath(new URL('../netlify/lib/audit-packages/', import.meta.url)));
