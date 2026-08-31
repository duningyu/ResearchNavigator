[CmdletBinding()]
param([string] $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path)

$ErrorActionPreference = 'Stop'
$csvPath = Join-Path $ProjectRoot 'deployment/PUBLIC_DEMO_SOAK.csv'
$statePath = Join-Path $ProjectRoot 'deployment/soak_monitor/PUBLIC_DEMO_SOAK_MONITOR_STATE.json'
if (-not (Test-Path -LiteralPath $csvPath)) { Write-Output 'Soak: CSV_MISSING'; exit 0 }
$rows = @(Import-Csv -LiteralPath $csvPath)
$elapsed = [Math]::Round((($rows | ForEach-Object { [double]$_.elapsed_minutes } | Measure-Object -Maximum).Maximum), 2)
$percent = [Math]::Round([Math]::Min($elapsed / 120 * 100, 100), 2)
$remaining = [Math]::Round([Math]::Max(120 - $elapsed, 0), 2)
$last = $rows[-1]
$health = @($rows | Where-Object { $_.vercel_http -ne '200' -or $_.local_api_http -ne '200' -or $_.tunnel_http -ne '200' -or $_.worker_status -ne 'ONLINE' -or -not [string]::IsNullOrWhiteSpace([string]$_.errors_since_last_sample) }).Count
$monitor = if (Test-Path -LiteralPath $statePath) { (Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json).monitor_status } else { 'NOT_STARTED' }
$process = if (Test-Path -LiteralPath $statePath) { (Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json).soak_process_state } else { 'UNKNOWN' }
Write-Output 'Soak:'
Write-Output "  $elapsed / 120 min"
Write-Output "  $percent%"
Write-Output "  remaining ~$remaining min"
Write-Output "  samples $($rows.Count)"
Write-Output "  latest sample $($last.timestamp)"
Write-Output "  health failures $health"
Write-Output "  process $process"
Write-Output "  monitor $monitor"
