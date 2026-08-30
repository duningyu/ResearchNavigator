[CmdletBinding()]
param([Parameter(Mandatory)] [string] $ProjectRoot)
$ErrorActionPreference = 'Stop'
$statePath = Join-Path (Resolve-Path $ProjectRoot) 'deployment/public_demo_state.json'
if (-not (Test-Path $statePath)) { Write-Output 'No public demo state found.'; exit 0 }
$state = Get-Content $statePath -Raw | ConvertFrom-Json
foreach ($pid in @($state.cloudflared_pid, $state.worker_pid, $state.api_pid)) {
  if ($pid) { $process = Get-Process -Id ([int]$pid) -ErrorAction SilentlyContinue; if ($process) { Stop-Process -Id $process.Id -Force } }
}
Remove-Item -LiteralPath $statePath -Force
