[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [Parameter(Mandatory)] [ValidateSet('Api', 'Worker')] [string] $Component,
  [string] $StatePath,
  [string] $PythonPath,
  [ValidateRange(0, 60)] [int] $PauseBeforeStartSeconds = 0
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd('\')
if (-not $StatePath) { $StatePath = Join-Path $project 'deployment/public_demo_state.json' }
$StatePath = [IO.Path]::GetFullPath($StatePath)
if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
  throw "Public demo state not found: $StatePath"
}
$state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
$demo = [IO.Path]::GetFullPath([string]$state.demo_data_dir).TrimEnd('\')
$markerPath = Join-Path $demo 'PUBLIC_DEMO_RUNTIME.marker'
if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
  throw 'Public demo runtime marker is missing.'
}
$marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
if ($marker.marker -ne 'RESEARCH_NAVIGATOR_PUBLIC_DEMO_RUNTIME_V1') {
  throw 'Public demo runtime marker is invalid.'
}
$markerProject = [IO.Path]::GetFullPath([string]$marker.project_root).TrimEnd('\')
if (-not $markerProject.Equals($project, [StringComparison]::OrdinalIgnoreCase)) {
  throw 'Public demo runtime marker belongs to another repository.'
}
if (-not $PythonPath) { $PythonPath = Join-Path $project '.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
  throw "Python environment not found: $PythonPath"
}

function Get-ProcessIdentity([Diagnostics.Process] $Process) {
  $Process.Refresh()
  $path = $null
  try { $path = $Process.Path } catch {}
  return [ordered]@{
    pid = $Process.Id
    creation_time = $Process.StartTime.ToUniversalTime().ToString('o')
    executable = $path
  }
}

function Get-MatchingProcess($Identity) {
  if (-not $Identity -or -not $Identity.pid -or -not $Identity.creation_time) { return $null }
  $process = Get-Process -Id ([int]$Identity.pid) -ErrorAction SilentlyContinue
  if (-not $process) { return $null }
  try {
    if ($Identity.creation_time -is [DateTime]) {
      $expected = $Identity.creation_time.ToUniversalTime()
    } else {
      $expected = [DateTime]::Parse(
        [string]$Identity.creation_time,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind
      ).ToUniversalTime()
    }
    if ([Math]::Abs(($process.StartTime.ToUniversalTime() - $expected).TotalSeconds) -ge 1) {
      return $null
    }
    if ($Identity.executable) {
      try {
        if (-not $process.Path.Equals(
          [string]$Identity.executable, [StringComparison]::OrdinalIgnoreCase
        )) { return $null }
      } catch { return $null }
    }
    return $process
  } catch { return $null }
}

function Get-OwnedProcessTree([int] $RootPid) {
  $all = @(Get-CimInstance Win32_Process)
  $queue = @([pscustomobject]@{ pid = $RootPid; depth = 0 })
  $result = @()
  while ($queue.Count -gt 0) {
    $current = $queue[0]
    if ($queue.Count -eq 1) { $queue = @() } else { $queue = @($queue[1..($queue.Count - 1)]) }
    $cim = $all | Where-Object ProcessId -eq $current.pid | Select-Object -First 1
    $process = Get-Process -Id ([int]$current.pid) -ErrorAction SilentlyContinue
    if ($process -and $cim -and $cim.Name -ne 'conhost.exe') {
      $identity = Get-ProcessIdentity $process
      $result += [pscustomobject]@{
        pid = $identity.pid
        parent_pid = [int]$cim.ParentProcessId
        depth = [int]$current.depth
        creation_time = $identity.creation_time
        executable = $identity.executable
        command_line = [string]$cim.CommandLine
      }
    }
    foreach ($child in @($all | Where-Object ParentProcessId -eq $current.pid)) {
      $queue += [pscustomobject]@{ pid = [int]$child.ProcessId; depth = [int]$current.depth + 1 }
    }
  }
  return @($result)
}

function Test-PortInUse([int] $Port) {
  $client = [Net.Sockets.TcpClient]::new()
  try {
    $task = $client.ConnectAsync('127.0.0.1', $Port)
    return $task.Wait(500) -and $client.Connected
  } catch { return $false } finally { $client.Dispose() }
}

function Test-LocalHealth([int] $Port) {
  try {
    $response = Invoke-WebRequest "http://127.0.0.1:$Port/api/health" `
      -UseBasicParsing -TimeoutSec 3
    return $response.StatusCode -eq 200
  } catch { return $false }
}

$componentName = $Component.ToLowerInvariant()
$treeProperty = "${componentName}_process_tree"
$identityProperty = "${componentName}_process"
$pidProperty = "${componentName}_pid"
$owned = @($state.$treeProperty | Where-Object { $_ -and $_.pid })
if ($owned.Count -eq 0 -and $state.$identityProperty) {
  $owned = @($state.$identityProperty)
}
if ($owned.Count -eq 0) { throw "No owned $Component process identity is recorded." }
$owned = @($owned | Sort-Object -Property @{ Expression = { [int]$_.depth }; Descending = $true })
foreach ($identity in $owned) {
  $process = Get-MatchingProcess $identity
  if ($process) { & taskkill.exe /PID $process.Id /F 2>$null | Out-Null }
}
$deadline = (Get-Date).AddSeconds(15)
do {
  $survivors = @($owned | Where-Object { Get-MatchingProcess $_ })
  if ($survivors.Count -eq 0) { break }
  Start-Sleep -Milliseconds 200
} while ((Get-Date) -lt $deadline)
if ($survivors.Count -ne 0) { throw "Owned $Component processes did not exit." }

$apiPort = [int]$state.api_port
if ($Component -eq 'Api') {
  $deadline = (Get-Date).AddSeconds(10)
  while ((Get-Date) -lt $deadline -and (Test-PortInUse $apiPort)) {
    Start-Sleep -Milliseconds 200
  }
  if (Test-PortInUse $apiPort) { throw "API port $apiPort was not released." }
}
if ($PauseBeforeStartSeconds -gt 0) { Start-Sleep -Seconds $PauseBeforeStartSeconds }

$databasePath = Join-Path $demo 'research_navigator.db'
$databaseUrlPath = $databasePath.Replace('\', '/')
$vercelOrigin = ([uri][string]$state.vercel_origin).AbsoluteUri.TrimEnd('/')
$env:RN_DATA_DIR = $demo
$env:RN_DATABASE_URL = "sqlite+pysqlite:///$databaseUrlPath"
$env:RN_UPLOAD_DIR = Join-Path $demo 'uploads'
$env:RN_VECTOR_DIR = Join-Path $demo 'vector_index'
$env:RN_BACKUP_DIR = Join-Path $demo 'backups'
$env:RN_CORS_ALLOWED_ORIGINS = $vercelOrigin
$env:RN_ALLOWED_ORIGINS = $vercelOrigin
$env:RN_ENVIRONMENT = 'demo'
$env:RN_PUBLIC_DEMO_MODE = '1'
$env:RN_PUBLIC_DEMO_MAX_USERS = '50'
$env:RN_PUBLIC_DEMO_MAX_UPLOAD_MB = '10'
$env:RN_PUBLIC_DEMO_MAX_ACTIVE_JOBS = '5'
$env:RN_PUBLIC_DEMO_MAX_QUERY_LENGTH = '200'
$env:RN_PUBLIC_DEMO_MAX_JOB_PAYLOAD_BYTES = '16384'
$env:RN_ENABLE_FIXTURE_SOURCE = '1'
$env:RN_ENABLE_OPENALEX = '0'
$env:RN_ENABLE_CROSSREF = '0'
$env:RN_ENABLE_ARXIV = '0'
$env:RN_ENABLE_SEMANTIC_SCHOLAR = '0'
$env:RN_ANALYSIS_PROVIDER = 'deterministic'
$env:PYTHONPATH = "$(Join-Path $project 'apps/api');$project"
$logs = Join-Path $demo 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null

if ($Component -eq 'Api') {
  $started = Start-Process -FilePath $PythonPath `
    -ArgumentList '-m','uvicorn','research_navigator.main:app','--host','127.0.0.1','--port',"$apiPort" `
    -WorkingDirectory $project -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs 'api.log') `
    -RedirectStandardError (Join-Path $logs 'api-error.log')
  $deadline = (Get-Date).AddSeconds(45)
  while ((Get-Date) -lt $deadline -and -not (Test-LocalHealth $apiPort)) {
    if ($started.HasExited) { throw 'API exited before readiness during restart.' }
    Start-Sleep -Milliseconds 250
  }
  if (-not (Test-LocalHealth $apiPort)) { throw 'API did not become ready after restart.' }
} else {
  $started = Start-Process -FilePath $PythonPath `
    -ArgumentList '-m','services.worker.main','--poll-seconds','2' `
    -WorkingDirectory $project -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs 'worker.log') `
    -RedirectStandardError (Join-Path $logs 'worker-error.log')
  Start-Sleep -Milliseconds 500
  if ($started.HasExited) { throw 'Worker exited during restart.' }
}

$state.$pidProperty = $started.Id
$state.$identityProperty = Get-ProcessIdentity $started
$state.$treeProperty = @(Get-OwnedProcessTree $started.Id)
$state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StatePath -Encoding utf8
Add-Content -LiteralPath (Join-Path $logs 'deployment.log') -Value (
  "$(Get-Date -Format o) RESTARTED component=$Component pid=$($started.Id)"
)
Write-Output "PUBLIC_DEMO_${($Component.ToUpperInvariant())}_RESTART=PASS"
