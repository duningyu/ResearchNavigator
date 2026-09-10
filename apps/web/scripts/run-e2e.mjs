import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import net from 'node:net';
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
const vite = resolve(webDir, 'node_modules', 'vite', 'bin', 'vite.js');
const dataDir = mkdtempSync(resolve(tmpdir(), 'research-navigator-e2e-'));
const runtimeImage = process.env.RN_E2E_DOCKER_IMAGE ?? 'rn223-schema-audit:py312-libsql020';
const children = [];
const containers = [];
let cleanupStarted = false;
let playwrightExit = 1;
let apiPort = 0;
let webPort = 0;
let baseUrl = '';
let env;
let runtime;
const receiptPath = process.env.RN_E2E_RECEIPT_PATH
  ? resolve(process.env.RN_E2E_RECEIPT_PATH)
  : resolve(root, 'codex_audit', 'E2E_TEARDOWN_RECEIPT.json');

const dependencySmoke = "import fastapi, sqlalchemy, uvicorn, research_navigator; print(sys.version)";

function runSync(command, args, options = {}) {
  return spawnSync(command, args, {
    cwd: root,
    encoding: 'utf8',
    windowsHide: true,
    ...options,
  });
}

function smokeHostPython(command, prefixArgs = []) {
  const result = runSync(command, [...prefixArgs, '-c', `import sys; ${dependencySmoke}`], {
    env: { ...process.env, PYTHONPATH: 'apps/api;.' },
  });
  if (result.status !== 0) return null;
  const version = String(result.stdout ?? '').trim().split(/\r?\n/).at(-1) ?? '';
  return { kind: 'host', command, prefixArgs, version, method: `validated_host:${command}` };
}

function smokeDockerRuntime() {
  const image = runSync('docker', ['image', 'inspect', runtimeImage]);
  if (image.status !== 0) return null;
  const repoMount = root.replaceAll('\\', '/');
  const result = runSync('docker', [
    'run', '--rm', '--network', 'none',
    '--mount', `type=bind,source=${repoMount},target=/workspace,readonly`,
    '--workdir', '/workspace',
    '--env', 'PYTHONPATH=/workspace/apps/api:/workspace',
    '--entrypoint', '/opt/rn-venv/bin/python',
    runtimeImage, '-c', `import sys; ${dependencySmoke}`,
  ]);
  if (result.status !== 0) return null;
  const version = String(result.stdout ?? '').trim().split(/\r?\n/).at(-1) ?? '';
  return { kind: 'docker', image: runtimeImage, version, method: `verified_docker:${runtimeImage}` };
}

function resolveRuntime() {
  const explicitPython = process.env.RN_E2E_PYTHON;
  const hostCandidates = [];
  if (explicitPython) hostCandidates.push({ command: explicitPython, prefixArgs: [] });
  hostCandidates.push({ command: resolve(root, '.venv', 'Scripts', 'python.exe'), prefixArgs: [] });
  if (process.platform === 'win32') hostCandidates.push({ command: 'py', prefixArgs: ['-3.12'] });
  hostCandidates.push({ command: 'python', prefixArgs: [] });
  hostCandidates.push({ command: 'python3', prefixArgs: [] });
  for (const candidate of hostCandidates) {
    const resolved = smokeHostPython(candidate.command, candidate.prefixArgs);
    if (resolved) return resolved;
  }
  const docker = smokeDockerRuntime();
  if (docker) return docker;
  throw new Error('No validated E2E Python runtime found: host Python candidates and verified Docker image failed dependency smoke.');
}

function availablePort(preferredPort) {
  return new Promise((resolvePort, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(preferredPort, '127.0.0.1', () => {
      const address = server.address();
      const selectedPort = typeof address === 'object' && address ? address.port : preferredPort;
      server.close((closeError) => closeError ? reject(closeError) : resolvePort(selectedPort));
    });
  });
}

async function selectPort(preferredPort) {
  try {
    return await availablePort(preferredPort);
  } catch {
    return availablePort(0);
  }
}

function dockerRun(args) {
  const result = runSync('docker', args);
  if (result.status !== 0) {
    throw new Error(`docker ${args.join(' ')} failed: ${String(result.stderr ?? result.stdout ?? '').trim()}`);
  }
  return String(result.stdout ?? '').trim();
}

function startDockerContainer(role, commandArgs) {
  const name = `rnux-e2-${role}-${process.pid}-${Date.now()}`;
  const repoMount = root.replaceAll('\\', '/');
  const runtimeMount = dataDir.replaceAll('\\', '/');
  const publishArgs = role === 'api' ? ['--publish', `${apiPort}:8000`] : [];
  const containerId = dockerRun([
    'run', '-d', '--name', name,
    ...publishArgs,
    '--mount', `type=bind,source=${repoMount},target=/workspace,readonly`,
    '--mount', `type=bind,source=${runtimeMount},target=/e2e-runtime`,
    '--workdir', '/workspace',
    '--env', 'PYTHONPATH=/workspace/apps/api:/workspace',
    '--env', 'RN_DATA_DIR=/e2e-runtime',
    '--env', 'RN_ENVIRONMENT=test',
    '--env', 'RN_ENABLE_FIXTURE_SOURCE=true',
    '--env', 'RN_ENABLE_OPENALEX=false',
    '--env', 'RN_ENABLE_CROSSREF=false',
    '--env', 'RN_ENABLE_ARXIV=false',
    '--env', 'RN_ENABLE_SEMANTIC_SCHOLAR=false',
    '--env', 'RN_ANALYSIS_PROVIDER=deterministic',
    '--env', `RN_ALLOWED_ORIGINS=${baseUrl},http://localhost:${webPort}`,
    '--env', 'LLM_BASE_URL=',
    '--env', 'LLM_API_KEY=',
    '--env', 'LLM_MODEL=',
    '--entrypoint', '/opt/rn-venv/bin/python',
    runtime.image,
    ...commandArgs,
  ]);
  containers.push({ name, containerId, role });
  return name;
}

function startBackend(role, args) {
  if (runtime.kind === 'docker') {
    return startDockerContainer(role, args);
  }
  return start(runtime.command, [...runtime.prefixArgs, ...args], root);
}

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

async function waitForPortReleased(port, label) {
  if (!port) return;
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    if (verifyPortReleased(port)) return;
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  assert.equal(verifyPortReleased(port), true, `${label} port must be released`);
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
  for (const container of [...containers].reverse()) {
    const result = runSync('docker', ['rm', '-f', container.name]);
    if (result.status !== 0 && !String(result.stderr ?? '').includes('No such container')) {
      throw new Error(`docker rm -f ${container.name} failed: ${String(result.stderr ?? result.stdout ?? '').trim()}`);
    }
  }
  await waitForPortReleased(apiPort, 'API');
  await waitForPortReleased(webPort, 'Web');
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
    runtime_resolution: runtime ?? null,
    backend_runtime: runtime?.kind ?? null,
    api_port: apiPort,
    web_port: webPort,
    base_url: baseUrl,
    docker_containers: containers.map((container) => ({ ...container })),
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
    runtime = resolveRuntime();
    apiPort = await selectPort(Number(process.env.RN_E2E_API_PORT ?? 8000));
    webPort = await selectPort(Number(process.env.RN_E2E_WEB_PORT ?? 5173));
    baseUrl = `http://127.0.0.1:${webPort}`;
    env = {
      ...process.env,
      RN_E2E_BASE_URL: baseUrl,
      VITE_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}`,
      PYTHONPATH: 'apps/api;.',
      RN_DATA_DIR: dataDir,
      RN_ENVIRONMENT: 'test',
      RN_ENABLE_FIXTURE_SOURCE: 'true',
      RN_ENABLE_OPENALEX: 'false',
      RN_ENABLE_CROSSREF: 'false',
      RN_ENABLE_ARXIV: 'false',
      RN_ENABLE_SEMANTIC_SCHOLAR: 'false',
      RN_ANALYSIS_PROVIDER: 'deterministic',
      RN_ALLOWED_ORIGINS: `${baseUrl},http://localhost:${webPort}`,
      LLM_BASE_URL: '',
      LLM_API_KEY: '',
      LLM_MODEL: '',
    };
    startBackend('api', ['-m', 'uvicorn', 'research_navigator.main:app', '--host', '0.0.0.0', '--port', '8000']);
    await waitFor(`http://127.0.0.1:${apiPort}/api/health`, 'api');
    startBackend('worker', ['-m', 'services.worker.main', '--poll-seconds', '0.5']);
    if (process.env.RN_E2E_FORCE_STARTUP_FAILURE === '1') {
      throw new Error('deterministic E2E startup failure requested');
    }
    start(process.execPath, [vite, '--host', '127.0.0.1', '--port', String(webPort)], webDir);
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
