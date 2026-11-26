import { context } from 'esbuild';

const build = await context({ entryPoints: ['web/app.js'], bundle: true, format: 'esm', outfile: 'public/app.js' });
await build.watch();
await build.serve({ servedir: 'public', host: '127.0.0.1', port: 8890 });
