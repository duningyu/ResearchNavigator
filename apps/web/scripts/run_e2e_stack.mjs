import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const webDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(webDir, '..', '..');
const python = resolve(root, '.venv', 'Scripts', 'python.exe');
const dataDir = mkdtempSync(resolve(tmpdir(), 'research-navigator-e2e-'));
const env = {
  ...process.env,
  PYTHONPATH: 'apps/api:.',
  RN_DATA_DIR: dataDir,
  RN_ENVIRONMENT: 'test',
  RN_ENABLE_FIXTURE_SOURCE: 'true',
  RN_ENABLE_OPENALEX: 'false',
  RN_ENABLE_CROSSREF: 'false',
  RN_ENABLE_ARXIV: 'false',
  RN_ENABLE_SEMANTIC_SCHOLAR: 'false',
  RN_ALLOWED_ORIGINS: 'http://127.0.0.1:5173,http://localhost:5173',
  VITE_API_PROXY_TARGET: 'http://127.0.0.1:8000',
};

const children = [];
function start(command, args, cwd) {
  const child = spawn(command, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  child.stdout.on('data', (chunk) => process.stdout.write(`[e2e:${args[0]}] ${chunk}`));
  child.stderr.on('data', (chunk) => process.stderr.write(`[e2e:${args[0]}] ${chunk}`));
  children.push(child);
  return child;
}

async function waitFor(url, label) {
  const deadline = Date.now() + 60_000;
  let lastError = 'not attempted';
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) { console.log(`ready ${label}`); return; }
      lastError = `HTTP ${response.status}`;
    } catch (error) { lastError = String(error); }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error(`${label} readiness timeout: ${lastError}`);
}

function teardown() {
  for (const child of children) child.kill('SIGTERM');
  try { rmSync(dataDir, { recursive: true, force: true }); } catch { /* best effort cleanup */ }
}

process.on('SIGINT', () => { teardown(); process.exit(130); });
process.on('SIGTERM', () => { teardown(); process.exit(143); });

start(python, ['-m', 'uvicorn', 'research_navigator.main:app', '--host', '127.0.0.1', '--port', '8000'], root);
start(python, ['-m', 'services.worker.main', '--poll-seconds', '0.5'], root);
const webCommand = process.platform === 'win32' ? 'cmd.exe' : 'corepack';
const webArgs = process.platform === 'win32'
  ? ['/d', '/s', '/c', 'corepack pnpm run dev -- --host 127.0.0.1 --port 5173']
  : ['pnpm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173'];
start(webCommand, webArgs, webDir);

try {
  await waitFor('http://127.0.0.1:8000/api/health', 'api');
  await waitFor('http://127.0.0.1:5173/', 'web');
  await new Promise(() => {});
} catch (error) {
  console.error(error);
  teardown();
  process.exit(1);
}
