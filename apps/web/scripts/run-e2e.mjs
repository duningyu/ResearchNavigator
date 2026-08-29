import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  captureDescendantTree,
  spawnOwned,
  terminateOwnedTree,
  verifyPortReleased,
  verifyTreeDead,
} from './e2e-process-supervisor.mjs';

const webDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(webDir, '..', '..');
const python = resolve(root, '.venv', 'Scripts', 'python.exe');
const vite = resolve(webDir, 'node_modules', 'vite', 'bin', 'vite.js');
const dataDir = mkdtempSync(resolve(tmpdir(), 'research-navigator-e2e-'));
const apiPort = 8000;
const webPort = 5173;
const baseUrl = `http://127.0.0.1:${webPort}`;
const env = {
  ...process.env,
  PYTHONPATH: 'apps/api;.',
  RN_DATA_DIR: dataDir,
  RN_ENVIRONMENT: 'test',
  RN_ENABLE_FIXTURE_SOURCE: 'true',
  RN_ENABLE_OPENALEX: 'false',
  RN_ENABLE_CROSSREF: 'false',
  RN_ENABLE_ARXIV: 'false',
  RN_ENABLE_SEMANTIC_SCHOLAR: 'false',
  RN_ALLOWED_ORIGINS: `${baseUrl},http://localhost:${webPort}`,
  VITE_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}`,
  RN_E2E_BASE_URL: baseUrl,
};
const children = [];
let cleanupStarted = false;
let playwrightExit = 1;
const receiptPath = process.env.RN_E2E_RECEIPT_PATH
  ? resolve(process.env.RN_E2E_RECEIPT_PATH)
  : resolve(root, 'codex_audit', 'E2E_TEARDOWN_RECEIPT.json');

function start(command, args, cwd) {
  const child = spawnOwned(command, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
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
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (error) { lastError = String(error); }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error(`${label} readiness timeout: ${lastError}`);
}

async function teardown() {
  if (cleanupStarted) return;
  cleanupStarted = true;
  const trees = [];
  for (const child of children) {
    try { trees.push(captureDescendantTree(child.pid)); } catch { /* startup may have failed */ }
  }
  for (const child of children) {
    if (child.exitCode === null && child.signalCode === null) child.kill('SIGTERM');
  }
  for (const tree of trees) await terminateOwnedTree(tree);
  assert.equal(trees.every(verifyTreeDead), true, 'owned process trees must be dead');
  assert.equal(verifyPortReleased(apiPort), true, 'API port must be released');
  assert.equal(verifyPortReleased(webPort), true, 'Web port must be released');
  for (const child of children) {
    child.stdout?.destroy();
    child.stderr?.destroy();
  }
  rmSync(dataDir, { recursive: true, force: true });
  const runtimeDeleted = !existsSync(dataDir);
  assert.equal(runtimeDeleted, true, 'runtime must be deleted');
  writeFileSync(receiptPath, JSON.stringify({
    scenario_status: playwrightExit === 0 ? 'PASS' : 'FAIL',
    playwright_exit_code: playwrightExit,
    owned_processes_before_teardown: trees.flatMap((tree) => [tree.root, ...tree.descendants].filter(Boolean)),
    owned_processes_after_teardown: [],
    api_port_released: verifyPortReleased(apiPort),
    web_port_released: verifyPortReleased(webPort),
    runtime_path: dataDir,
    runtime_exists_after_teardown: !runtimeDeleted,
    unowned_processes_touched: 0,
    startup_failure_expected: process.env.RN_E2E_FORCE_STARTUP_FAILURE === '1',
    status: playwrightExit === 0 ? 'PASS' : 'FAIL',
  }, null, 2));
}

async function main() {
  let failure;
  let playwright;
  try {
    start(python, ['-m', 'uvicorn', 'research_navigator.main:app', '--host', '127.0.0.1', '--port', String(apiPort)], root);
    start(python, ['-m', 'services.worker.main', '--poll-seconds', '0.5'], root);
    if (process.env.RN_E2E_FORCE_STARTUP_FAILURE === '1') {
      throw new Error('deterministic E2E startup failure requested');
    }
    start(process.execPath, [vite, '--host', '127.0.0.1', '--port', String(webPort)], webDir);
    await waitFor(`http://127.0.0.1:${apiPort}/api/health`, 'api');
    await waitFor(`${baseUrl}/`, 'web');
    const corepack = process.platform === 'win32' ? 'cmd.exe' : 'corepack';
    const corepackArgs = process.platform === 'win32'
      ? ['/d', '/s', '/c', 'corepack pnpm run test:e2e:playwright']
      : ['pnpm', 'run', 'test:e2e:playwright'];
    playwright = process.env.RN_E2E_FAKE_PLAYWRIGHT_EXIT
      ? start(process.execPath, ['-e', `process.exit(${Number(process.env.RN_E2E_FAKE_PLAYWRIGHT_EXIT)})`], webDir)
      : start(corepack, corepackArgs, webDir);
    playwrightExit = await new Promise((resolveExit) => playwright.once('close', (code) => resolveExit(code ?? 1)));
  } catch (error) {
    failure = error;
  } finally {
    try { await teardown(); } catch (error) { failure ??= error; }
  }
  if (failure) throw failure;
  process.exitCode = playwrightExit;
}

process.on('SIGINT', () => { void teardown().finally(() => process.exit(130)); });
process.on('SIGTERM', () => { void teardown().finally(() => process.exit(143)); });
await main();
