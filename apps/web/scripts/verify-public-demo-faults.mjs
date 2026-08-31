import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '@playwright/test';

const webDir = resolve(import.meta.dirname, '..');
const root = resolve(webDir, '..', '..');
const statePath = resolve(root, 'deployment', 'public_demo_state.json');
const supervisor = resolve(root, 'scripts', 'deployment', 'restart_public_demo_component.ps1');
const receiptPath = resolve(root, 'deployment', 'ownership_forensics', 'API_WORKER_FAULT_INJECTION.json');
const email = process.env.RN_PUBLIC_DEMO_EMAIL ?? 'demo@researchnavigator.local';
const password = process.env.RN_PUBLIC_DEMO_PASSWORD ?? 'research-demo-223';

function state() {
  return JSON.parse(readFileSync(statePath, 'utf8'));
}

function sameIdentity(left, right) {
  return left.pid === right.pid && left.creation_time_utc === right.creation_time_utc;
}

function runSupervisor(component, extra = []) {
  return new Promise((resolveRun, reject) => {
    const child = spawn('pwsh', [
      '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', supervisor,
      '-ProjectRoot', root, '-StatePath', statePath, '-Component', component, ...extra,
    ], { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.once('error', reject);
    child.once('exit', (code) => {
      child.stdout.destroy();
      child.stderr.destroy();
      if (code === 0) resolveRun(stdout.trim());
      else reject(new Error(`Supervisor ${component} failed (${code}): ${stderr || stdout}`));
    });
  });
}

async function api(path, options = {}) {
  const current = state();
  const response = await fetch(`${current.tunnel_origin}/api${path}`, options);
  const text = await response.text();
  let body = null;
  if (text) body = JSON.parse(text);
  if (!response.ok) throw new Error(`API ${path} failed: HTTP ${response.status}`);
  return body;
}

async function waitForTerminal(jobId, token) {
  const deadline = Date.now() + 45_000;
  while (Date.now() < deadline) {
    const job = await api(`/jobs/${jobId}`, { headers: { Authorization: `Bearer ${token}` } });
    if (job.terminal) return job;
    await new Promise((resolveWait) => setTimeout(resolveWait, 500));
  }
  throw new Error(`Job ${jobId} did not become terminal.`);
}

const beforeApi = state();
const browser = await chromium.launch({ channel: process.env.RN_E2E_BROWSER_CHANNEL ?? 'chrome' });
const page = await browser.newPage();
page.setDefaultTimeout(30_000);
let offlineObserved = false;
let recoveredAfterRetry = false;
let restartApi;
try {
  console.log('FAULT_TEST_PHASE=LOGIN');
  await page.goto(beforeApi.share_url, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('邮箱').fill(email);
  await page.getByLabel('密码').fill(password);
  await page.getByRole('button', { name: /^登\s*录$/ }).click();
  await page.getByRole('heading', { name: '今日研究起点' }).waitFor({ timeout: 30_000 });

  console.log('FAULT_TEST_PHASE=API_RESTART');
  restartApi = runSupervisor('Api', ['-PauseBeforeStartSeconds', '30']);
  await page.getByRole('heading', { name: 'ResearchNavigator 演示当前离线' }).waitFor({ timeout: 45_000 });
  await page.getByTestId('backend-status').filter({ hasText: 'BACKEND_OFFLINE' }).waitFor({ timeout: 45_000 });
  offlineObserved = true;
  console.log('FAULT_TEST_PHASE=OFFLINE_OBSERVED');
  await restartApi;
  console.log('FAULT_TEST_PHASE=API_RESTARTED');
  await page.getByRole('button', { name: '重试连接' }).click({ timeout: 10_000 });
  await page.getByRole('heading', { name: '今日研究起点' }).waitFor({ timeout: 30_000 });
  recoveredAfterRetry = true;
  console.log('FAULT_TEST_PHASE=UI_RECOVERED');
} finally {
  if (restartApi) await restartApi;
  await browser.close();
}
const afterApi = state();
assert.equal(sameIdentity(beforeApi.worker_process, afterApi.worker_process), true);
assert.equal(sameIdentity(beforeApi.cloudflared_process, afterApi.cloudflared_process), true);
assert.equal(sameIdentity(beforeApi.api_process, afterApi.api_process), false);

const login = await api('/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password }),
});
const token = login.access_token;
assert.equal(typeof token, 'string');
const beforeWorker = state();
console.log('FAULT_TEST_PHASE=WORKER_STOP');
await runSupervisor('Worker', ['-StopOnly']);
const created = await api('/jobs', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    'Idempotency-Key': `public-demo-worker-restart-${Date.now()}`,
  },
  body: JSON.stringify({ job_type: 'noop', payload: { validation: 'worker_restart' } }),
});
assert.equal(created.terminal, false);
console.log('FAULT_TEST_PHASE=WORKER_RESTART');
await runSupervisor('Worker');
const terminalJob = await waitForTerminal(created.id, token);
console.log('FAULT_TEST_PHASE=JOB_TERMINAL');
const afterWorker = state();
assert.equal(sameIdentity(beforeWorker.api_process, afterWorker.api_process), true);
assert.equal(sameIdentity(beforeWorker.cloudflared_process, afterWorker.cloudflared_process), true);
assert.equal(sameIdentity(beforeWorker.worker_process, afterWorker.worker_process), false);

writeFileSync(receiptPath, JSON.stringify({
  tested_at_utc: new Date().toISOString(),
  browser_channel: process.env.RN_E2E_BROWSER_CHANNEL ?? 'chrome',
  api_restart: {
    status: 'PASS',
    offline_observed: offlineObserved,
    recovered_after_retry: recoveredAfterRetry,
    api_identity_changed: true,
    worker_identity_unchanged: true,
    tunnel_identity_unchanged: true,
  },
  worker_restart: {
    status: 'PASS',
    pending_job_id: created.id,
    terminal_status: terminalJob.status,
    worker_identity_changed: true,
    api_identity_unchanged: true,
    tunnel_identity_unchanged: true,
  },
  secrets_recorded: false,
}, null, 2));
console.log('PUBLIC_DEMO_API_WORKER_FAULTS=PASS');
