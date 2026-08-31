[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [Parameter(Mandatory)] [int] $SoakPid,
  [int] $TargetMinutes = 120,
  [int] $PollSeconds = 60,
  [string] $SoakCsv,
  [string] $SoakStdout,
  [string] $SoakStderr,
  [string] $StatePath,
  [string] $LogPath,
  [string] $RuntimePath,
  [string] $IdentityPath,
  [string] $TerminalReceipt,
  [switch] $Once,
  [switch] $SkipContextGuard,
  [ValidateSet('LIVE','RUNNING_MATCH','RUNNING_MISMATCH','ABSENT')]
  [string] $ProcessStateOverride = 'LIVE'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd('\')
if (-not $SkipContextGuard) {
  & (Join-Path $root 'scripts/deployment/assert_researchnavigator_context.ps1') -ProjectRoot $root -Quiet
  if ($LASTEXITCODE -ne 0) { throw 'ResearchNavigator execution context guard refused monitor.' }
}
$monitorDir = Join-Path $root 'deployment/soak_monitor'
New-Item -ItemType Directory -Path $monitorDir -Force | Out-Null
if (-not $SoakCsv) { $SoakCsv = Join-Path $root 'deployment/PUBLIC_DEMO_SOAK.csv' }
if (-not $SoakStderr) { $SoakStderr = Join-Path $root 'deployment/PUBLIC_DEMO_SOAK_DETACHED_20260831-211831.log.err' }
if (-not $StatePath) { $StatePath = Join-Path $monitorDir 'PUBLIC_DEMO_SOAK_MONITOR_STATE.json' }
if (-not $LogPath) { $LogPath = Join-Path $monitorDir 'PUBLIC_DEMO_SOAK_MONITOR.log' }
if (-not $RuntimePath) { $RuntimePath = Join-Path $monitorDir 'SOAK_MONITOR_RUNTIME.json' }
if (-not $IdentityPath) { $IdentityPath = Join-Path $monitorDir 'SOAK_MONITOR_PROCESS_IDENTITY.json' }
if (-not $TerminalReceipt) { $TerminalReceipt = Join-Path (Split-Path -Parent $SoakCsv) 'PUBLIC_DEMO_SOAK_TERMINAL.json' }

function Get-Hash([string] $Value) {
  $sha = [Security.Cryptography.SHA256]::Create()
  try { return ([Convert]::ToHexString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value))).ToLowerInvariant()) }
  finally { $sha.Dispose() }
}

function Get-ProcessSnapshot {
  if ($ProcessStateOverride -eq 'ABSENT') { return [pscustomobject]@{ state='ABSENT'; match=$false; creation_time_utc=$null; process_name=$null; command_line_hash=$null } }
  if ($ProcessStateOverride -eq 'RUNNING_MATCH') { return [pscustomobject]@{ state='RUNNING'; match=$true; creation_time_utc='synthetic'; process_name='synthetic'; command_line_hash='synthetic' } }
  if ($ProcessStateOverride -eq 'RUNNING_MISMATCH') { return [pscustomobject]@{ state='RUNNING'; match=$false; creation_time_utc='synthetic-mismatch'; process_name='synthetic'; command_line_hash='synthetic' } }
  $p = Get-Process -Id $SoakPid -ErrorAction SilentlyContinue
  if (-not $p) { return [pscustomobject]@{ state='ABSENT'; match=$false; creation_time_utc=$null; process_name=$null; command_line_hash=$null } }
  $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$SoakPid"
  $creation = $p.StartTime.ToUniversalTime().ToString('o')
  $command = if ($cim) { [string]$cim.CommandLine } else { '' }
  $expected = if (Test-Path -LiteralPath $IdentityPath) { (Get-Content $IdentityPath -Raw | ConvertFrom-Json).creation_time_utc } else { $creation }
  $match = [Math]::Abs((([DateTimeOffset]$creation).ToUniversalTime() - ([DateTimeOffset]$expected).ToUniversalTime()).TotalMilliseconds) -le 10
  [pscustomobject]@{ state='RUNNING'; match=$match; creation_time_utc=$creation; process_name=$p.ProcessName; command_line_hash=(Get-Hash $command) }
}

function Read-SoakRows {
  if (-not (Test-Path -LiteralPath $SoakCsv)) { return $null }
  try { return @(Import-Csv -LiteralPath $SoakCsv) } catch { throw "CSV_PARSE_ERROR: $($_.Exception.Message)" }
}

function Read-TerminalReceipt {
  if (-not (Test-Path -LiteralPath $TerminalReceipt)) { return $null }
  try { return Get-Content -LiteralPath $TerminalReceipt -Raw | ConvertFrom-Json } catch { return $null }
}

function Get-StderrInfo {
  if (-not (Test-Path -LiteralPath $SoakStderr)) { return [pscustomobject]@{ status='EMPTY'; last=$null } }
  $lines = @(Get-Content -LiteralPath $SoakStderr | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
  if ($lines.Count -eq 0) { return [pscustomobject]@{ status='EMPTY'; last=$null } }
  $last = [string]$lines[$lines.Count - 1]
  $fatal = $lines | Where-Object { $_ -match '(?i)unhandled exception|traceback|\bfatal\b|database corrupt|soak_fail' }
  [pscustomobject]@{ status=if ($fatal) { 'POTENTIAL_FATAL' } else { 'NON_FATAL' }; last=$last }
}

function Write-State {
  param([object] $State)
  $State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $StatePath -Encoding utf8
  ($State | ConvertTo-Json -Compress -Depth 8) | Add-Content -LiteralPath $LogPath -Encoding utf8
  if (-not $Once) { Write-Output "Elapsed: $($State.elapsed_minutes) / $TargetMinutes min | Progress: $($State.progress_percent)% | Remaining: $($State.remaining_minutes) min | Samples: $($State.csv_row_count) | Status: $($State.monitor_status)" }
}

function Invoke-Check {
  $checked = [DateTimeOffset]::UtcNow
  $process = Get-ProcessSnapshot
  $stderr = Get-StderrInfo
  $rows = Read-SoakRows
  $terminal = Read-TerminalReceipt
  $status = 'INITIALIZING'
  $elapsed = 0.0; $first = ''; $latest = ''; $age = $null; $healthFails = 0
  if ($null -eq $rows) { $status = 'CSV_MISSING' }
  else {
    try {
      $elapsed = [Math]::Max(0, [double](($rows | ForEach-Object { [double]$_.elapsed_minutes } | Measure-Object -Maximum).Maximum))
      $first = [string]$rows[0].timestamp; $latest = [string]$rows[$rows.Count - 1].timestamp
      $age = [Math]::Round(($checked - [DateTimeOffset]::Parse($latest)).TotalSeconds, 1)
      foreach ($row in $rows) {
        if (($row.PSObject.Properties.Name -contains 'vercel_http' -and $row.vercel_http -ne '200') -or ($row.PSObject.Properties.Name -contains 'local_api_http' -and $row.local_api_http -ne '200') -or ($row.PSObject.Properties.Name -contains 'tunnel_http' -and $row.tunnel_http -ne '200') -or ($row.PSObject.Properties.Name -contains 'worker_status' -and $row.worker_status -ne 'ONLINE') -or ($row.PSObject.Properties.Name -contains 'errors_since_last_sample' -and -not [string]::IsNullOrWhiteSpace([string]$row.errors_since_last_sample))) { $healthFails++ }
      }
      $targetReached = ($elapsed -ge $TargetMinutes -or ($terminal -and $terminal.normal_completion -eq $true))
      if (-not $process.match -and $process.state -eq 'RUNNING') { $status = 'PROCESS_IDENTITY_MISMATCH' }
      elseif ($targetReached) { $status = if ($process.state -eq 'RUNNING') { 'TARGET_REACHED_PROCESS_STILL_RUNNING' } else { 'TARGET_REACHED_PENDING_TERMINAL_VALIDATION' } }
      elseif ($process.state -eq 'ABSENT') { $status = 'PROCESS_EXITED_EARLY' }
      elseif ($stderr.status -eq 'POTENTIAL_FATAL') { $status = 'FATAL_LOG_DETECTED' }
      elseif ($age -gt 420) { $status = 'RUNNING_STALE_SAMPLE_WARNING' }
      else { $status = 'RUNNING' }
    } catch { $status = if ($_.Exception.Message -like 'CSV_PARSE_ERROR*') { 'CSV_PARSE_ERROR' } else { 'MONITOR_ERROR' } }
  }
  $state = [ordered]@{
    project='ResearchNavigator'; version='2.2.3'; monitor_status=$status; checked_at_utc=$checked.ToString('o')
    soak_pid=$SoakPid; soak_process_identity_match=[bool]$process.match; soak_process_state=$process.state
    target_minutes=$TargetMinutes; elapsed_minutes=[Math]::Round($elapsed,2); remaining_minutes=[Math]::Round([Math]::Max($TargetMinutes-$elapsed,0),2); progress_percent=[Math]::Round([Math]::Min(($elapsed/$TargetMinutes)*100,100),2)
    csv_path=$SoakCsv; csv_row_count=if($rows){$rows.Count}else{0}; first_sample_timestamp=$first; latest_sample_timestamp=$latest; latest_sample_age_seconds=$age
    health_failure_count=$healthFails; local_api_status=if($rows){[string]$rows[-1].local_api_http}else{''}; worker_status=if($rows){[string]$rows[-1].worker_status}else{''}; cloudflared_status=if($rows){[string]$rows[-1].tunnel_http}else{''}; public_api_status=if($rows){[string]$rows[-1].vercel_http}else{''}
    stderr_status=$stderr.status; stderr_last_nonempty_line=$stderr.last; terminal_receipt_status=if($terminal){[string]$terminal.exit_reason}else{'MISSING'}; target_reached=($elapsed -ge $TargetMinutes -or ($terminal -and $terminal.normal_completion -eq $true)); terminal_validation_required=$true; second_soak_started=$false
  }
  Write-State $state
  return $state
}

try {
  $monitorProcess = Get-Process -Id $PID -ErrorAction Stop
  [ordered]@{ monitor_pid=$PID; creation_time_utc=$monitorProcess.StartTime.ToUniversalTime().ToString('o'); process_name=$monitorProcess.ProcessName; started_at_utc=[DateTimeOffset]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $RuntimePath -Encoding utf8
} catch { }
if ($ProcessStateOverride -eq 'LIVE') {
  $snapshot = Get-ProcessSnapshot
  if ($snapshot.state -eq 'RUNNING') { [ordered]@{ soak_pid=$SoakPid; creation_time_utc=$snapshot.creation_time_utc; process_name=$snapshot.process_name; command_line_hash=$snapshot.command_line_hash; captured_at_utc=[DateTimeOffset]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $IdentityPath -Encoding utf8 }
}
do {
  $result = Invoke-Check
  if (-not $Once -and $result.monitor_status -notin @('CSV_MISSING','CSV_PARSE_ERROR','PROCESS_EXITED_EARLY','PROCESS_IDENTITY_MISMATCH','TARGET_REACHED_PENDING_TERMINAL_VALIDATION','FATAL_LOG_DETECTED')) { Start-Sleep -Seconds ([Math]::Max(1,$PollSeconds)) }
  else { break }
} while ($true)
