import { execFileSync, spawn } from 'node:child_process';

const powershell = 'powershell.exe';

function snapshot() {
  const command = "$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine,CreationDate,ExecutablePath | ConvertTo-Json -Depth 4";
  const output = execFileSync(powershell, ['-NoProfile', '-NonInteractive', '-Command', command], { encoding: 'utf8' });
  const value = JSON.parse(output || '[]');
  return (Array.isArray(value) ? value : [value]).filter((item) => item && Number(item.ProcessId) > 0);
}

function identity(item) {
  return {
    pid: Number(item.ProcessId),
    parent_pid: Number(item.ParentProcessId),
    creation_time: String(item.CreationDate ?? ''),
    command_line: String(item.CommandLine ?? ''),
    executable: String(item.ExecutablePath ?? ''),
    name: String(item.Name ?? ''),
  };
}

function same(expected, processes = snapshot().map(identity)) {
  const actual = processes.find((item) => item.pid === expected.pid);
  if (!actual) return false;
  return actual.creation_time === expected.creation_time
    && actual.command_line.trim().toLowerCase() === expected.command_line.trim().toLowerCase()
    && actual.executable.trim().toLowerCase() === expected.executable.trim().toLowerCase();
}

export function captureDescendantTree(rootPid) {
  const processes = snapshot().map(identity);
  const root = processes.find((item) => item.pid === Number(rootPid));
  if (!root) throw new Error(`cannot capture owned process root ${rootPid}`);
  const byParent = new Map();
  for (const process of processes) {
    const children = byParent.get(process.parent_pid) ?? [];
    children.push(process);
    byParent.set(process.parent_pid, children);
  }
  const descendants = [];
  const pending = [root.pid];
  while (pending.length) {
    const parent = pending.shift();
    for (const child of byParent.get(parent) ?? []) {
      descendants.push(child);
      pending.push(child.pid);
    }
  }
  return { root_pid: root.pid, root, descendants };
}

function depth(tree, pid) {
  let current = tree.descendants.find((item) => item.pid === pid);
  let result = 0;
  while (current) {
    result += 1;
    current = tree.descendants.find((item) => item.pid === current.parent_pid);
  }
  return result;
}

function killMatching(process) {
  if (process && same(process)) {
    execFileSync('taskkill.exe', ['/PID', String(process.pid), '/F'], { stdio: 'ignore' });
  }
}

export async function terminateOwnedTree(tree, timeoutMs = 15_000) {
  const all = [...tree.descendants, tree.root].sort((a, b) => depth(tree, b.pid) - depth(tree, a.pid));
  for (const process of all) {
    try { killMatching(process); } catch { /* already exited */ }
  }
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (all.every((process) => !same(process))) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`owned process tree did not exit: ${tree.root_pid}`);
}

export function verifyTreeDead(tree) {
  const processes = snapshot().map(identity);
  return [tree.root, ...tree.descendants].every((process) => !same(process, processes));
}

export function verifyPortReleased(port) {
  const command = `$ErrorActionPreference='SilentlyContinue'; @(Get-NetTCPConnection -State Listen -LocalPort ${Number(port)}).Count`;
  return Number(execFileSync(powershell, ['-NoProfile', '-NonInteractive', '-Command', command], { encoding: 'utf8' }).trim()) === 0;
}

export function spawnOwned(command, args, options) {
  return spawn(command, args, options);
}
