import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const webDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const orchestrator = resolve(webDir, 'scripts', 'run-e2e.mjs');
const root = resolve(webDir, '..', '..');
const sentinel = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore', windowsHide: true });
const evidenceDir = mkdtempSync(resolve(tmpdir(), 'research-navigator-failure-paths-'));

function run(label, extra) {
  const receipt = resolve(evidenceDir, `${label}.json`);
  return new Promise((resolveRun, reject) => {
    const child = spawn(process.execPath, [orchestrator], {
      cwd: webDir,
      env: { ...process.env, RN_E2E_RECEIPT_PATH: receipt, ...extra },
      stdio: 'ignore',
      windowsHide: true,
    });
    child.once('error', reject);
    child.once('close', (code) => {
      try { resolveRun({ code, receipt: JSON.parse(readFileSync(receipt, 'utf8')) }); }
      catch (error) { reject(error); }
    });
  });
}

try {
  const playwrightFailure = await run('playwright-failure', { RN_E2E_FAKE_PLAYWRIGHT_EXIT: '1' });
  assert.equal(playwrightFailure.code, 1);
  assert.equal(playwrightFailure.receipt.playwright_exit_code, 1);
  assert.equal(playwrightFailure.receipt.owned_processes_after_teardown.length, 0);
  assert.equal(playwrightFailure.receipt.api_port_released, true);
  assert.equal(playwrightFailure.receipt.web_port_released, true);
  assert.equal(playwrightFailure.receipt.runtime_exists_after_teardown, false);
  assert.equal(sentinel.exitCode, null);

  const startupFailure = await run('startup-failure', { RN_E2E_FORCE_STARTUP_FAILURE: '1' });
  assert.notEqual(startupFailure.code, 0);
  assert.equal(startupFailure.receipt.startup_failure_expected, true);
  assert.equal(startupFailure.receipt.owned_processes_after_teardown.length, 0);
  assert.equal(startupFailure.receipt.api_port_released, true);
  assert.equal(startupFailure.receipt.web_port_released, true);
  assert.equal(startupFailure.receipt.runtime_exists_after_teardown, false);
  assert.equal(sentinel.exitCode, null);

  const result = {
    playwright_failure_path: {
      status: 'PASS',
      playwright_exit_code: playwrightFailure.receipt.playwright_exit_code,
      owned_processes_after_teardown: [],
      ports_released: playwrightFailure.receipt.api_port_released && playwrightFailure.receipt.web_port_released,
      runtime_deleted: !playwrightFailure.receipt.runtime_exists_after_teardown,
      unowned_processes_touched: 0,
    },
    startup_failure_path: {
      status: 'PASS',
      startup_failure_expected: true,
      owned_processes_after_teardown: [],
      ports_released: startupFailure.receipt.api_port_released && startupFailure.receipt.web_port_released,
      runtime_deleted: !startupFailure.receipt.runtime_exists_after_teardown,
      unowned_processes_touched: 0,
    },
  };
  writeFileSync(resolve(root, 'codex_audit', 'E2E_FAILURE_PATH_RECEIPT.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
} finally {
  if (sentinel.exitCode === null) sentinel.kill();
  rmSync(evidenceDir, { recursive: true, force: true });
}
