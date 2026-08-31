[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [int] $DurationMinutes = 120,
  [int] $SampleIntervalMinutes = 5,
  [int] $ActionIntervalMinutes = 15,
  [string] $OutputPath
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd('\')
$guard = Join-Path $PSScriptRoot 'assert_researchnavigator_context.ps1'
& $guard -ProjectRoot $root -Quiet
if ($LASTEXITCODE -ne 0) { throw 'ResearchNavigator execution context guard refused soak.' }
$statePath = Join-Path $root 'deployment/public_demo_state.json'
if (-not $OutputPath) { $OutputPath = Join-Path $root 'deployment/PUBLIC_DEMO_SOAK.csv' }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json -DateKind String
$started = [DateTimeOffset]::UtcNow
$deadline = $started.AddMinutes($DurationMinutes)
$nextAction = $started
$rows = [Collections.Generic.List[object]]::new()
$errorsSinceLast = [Collections.Generic.List[string]]::new()

function Get-HttpCode([string] $Url) {
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15
    return [int]$response.StatusCode
  } catch {
    $errorsSinceLast.Add("HTTP ${Url}: $($_.Exception.GetType().Name)")
    return $null
  }
}

function Get-ProcessMetric([int] $ProcessId, [string] $CreationTimeUtc) {
  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if (-not $process) { return [pscustomobject]@{ alive=$false; creation_time_utc=$null; rss_mb=$null } }
  $creation = $process.StartTime.ToUniversalTime().ToString('o')
  $same = [Math]::Abs((([DateTimeOffset]$creation).ToUniversalTime() - ([DateTimeOffset]$CreationTimeUtc).ToUniversalTime()).TotalMilliseconds) -le 10
  return [pscustomobject]@{
    alive = [bool]$same
    creation_time_utc = $creation
    rss_mb = [Math]::Round($process.WorkingSet64 / 1MB, 3)
  }
}

function Get-ActiveJobs([string] $DatabasePath) {
  try {
    $python = Join-Path $root '.venv/Scripts/python.exe'
    $value = & $python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('select count(*) from jobs where status in (?,?)',('queued','running')).fetchone()[0])" $DatabasePath 2>$null
    if ($LASTEXITCODE -eq 0) { return [int]($value | Select-Object -Last 1) }
  } catch { }
  return $null
}

function Invoke-FixtureAction {
  try {
    $email = if ($env:RN_PUBLIC_DEMO_EMAIL) { $env:RN_PUBLIC_DEMO_EMAIL } else { 'demo@researchnavigator.local' }
    $password = if ($env:RN_PUBLIC_DEMO_PASSWORD) { $env:RN_PUBLIC_DEMO_PASSWORD } else { 'research-demo-223' }
    $login = Invoke-RestMethod -Uri "$($state.tunnel_origin)/api/auth/login" -Method Post -ContentType 'application/json' -Body (@{email=$email;password=$password}|ConvertTo-Json)
    $headers = @{ Authorization = "Bearer $($login.access_token)" }
    $null = Invoke-RestMethod -Uri "$($state.tunnel_origin)/api/sources/status" -Headers $headers
    $search = Invoke-RestMethod -Uri "$($state.tunnel_origin)/api/search/papers" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{query='anomaly detection';limit=1;sources=@('fixture')}|ConvertTo-Json)
    if ([int]$search.result_count -lt 1) { throw 'fixture search returned no result' }
  } catch { $errorsSinceLast.Add("FIXTURE_ACTION $($_.Exception.GetType().Name): $($_.Exception.Message)") }
}

while ([DateTimeOffset]::UtcNow -lt $deadline) {
  $now = [DateTimeOffset]::UtcNow
  if ($now -ge $nextAction) { Invoke-FixtureAction; $nextAction = $now.AddMinutes($ActionIntervalMinutes) }
  $live = Get-CimInstance Win32_Process
  $api = Get-ProcessMetric ([int]$state.api_process.pid) ([string]$state.api_process.creation_time_utc)
  $worker = Get-ProcessMetric ([int]$state.worker_process.pid) ([string]$state.worker_process.creation_time_utc)
  $tunnel = Get-ProcessMetric ([int]$state.cloudflared_process.pid) ([string]$state.cloudflared_process.creation_time_utc)
  $db = Get-Item -LiteralPath (Join-Path ([string]$state.demo_data_dir) 'research_navigator.db') -ErrorAction SilentlyContinue
  $row = [ordered]@{
    timestamp = $now.ToString('o')
    elapsed_minutes = [Math]::Round(($now-$started).TotalMinutes, 2)
    vercel_http = Get-HttpCode ([string]$state.vercel_origin)
    local_api_http = Get-HttpCode "http://127.0.0.1:$([int]$state.api_port)/api/health"
    tunnel_http = Get-HttpCode "$($state.tunnel_origin)/api/health"
    worker_status = if ($worker.alive) { 'ONLINE' } else { 'OFFLINE_OR_IDENTITY_MISMATCH' }
    api_pid = [int]$state.api_process.pid
    api_creation_time_utc = $api.creation_time_utc
    worker_pid = [int]$state.worker_process.pid
    worker_creation_time_utc = $worker.creation_time_utc
    cloudflared_pid = [int]$state.cloudflared_process.pid
    cloudflared_creation_time_utc = $tunnel.creation_time_utc
    api_rss_mb = $api.rss_mb
    worker_rss_mb = $worker.rss_mb
    cloudflared_rss_mb = $tunnel.rss_mb
    db_size_mb = if ($db) { [Math]::Round($db.Length / 1MB, 3) } else { $null }
    active_jobs = Get-ActiveJobs (Join-Path ([string]$state.demo_data_dir) 'research_navigator.db')
    errors_since_last_sample = ($errorsSinceLast -join ' | ')
  }
  $rows.Add([pscustomobject]$row)
  $errorsSinceLast.Clear()
  $rows | Export-Csv -LiteralPath $OutputPath -NoTypeInformation -Encoding utf8
  Write-Output (($row | ConvertTo-Json -Compress))
  $remaining = ($deadline - [DateTimeOffset]::UtcNow).TotalSeconds
  if ($remaining -le 0) { break }
  Start-Sleep -Seconds ([Math]::Min($SampleIntervalMinutes * 60, [int]$remaining))
}
Write-Output "SOAK_COMPLETE samples=$($rows.Count) output=$OutputPath"
