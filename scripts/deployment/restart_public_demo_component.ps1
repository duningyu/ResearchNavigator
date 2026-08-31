[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [Parameter(Mandatory)] [ValidateSet('Api', 'Worker', 'Cloudflared')] [string] $Component,
  [string] $StatePath,
  [string] $PythonPath,
  [ValidateRange(0, 60)] [int] $PauseBeforeStartSeconds = 0,
  [switch] $StopOnly,
  [switch] $DryRun
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd('\')
Import-Module (Join-Path $PSScriptRoot 'PublicDemoProcessOwnership.psm1') -Force
if (-not $StatePath) { $StatePath = Join-Path $project 'deployment/public_demo_state.json' }
$StatePath = [IO.Path]::GetFullPath($StatePath)
if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
  throw "Public demo state not found: $StatePath"
}
$state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json -DateKind String
$demo = [IO.Path]::GetFullPath([string]$state.demo_data_dir).TrimEnd('\')
$markerPath = Join-Path $demo 'PUBLIC_DEMO_RUNTIME.marker'
if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
  throw 'Public demo runtime marker is missing.'
}
$marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json -DateKind String
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

function Resolve-StoredComponent([string] $Name, $Live) {
  $identity = $state."${Name}_process"
  $match = Test-PublicDemoProcessIdentity $identity @($Live.processes)
  if (-not $match.matched) {
    return [pscustomobject][ordered]@{
      root_trusted=$false; classification=$match.classification
      accepted_tree=@(); rejected_edges=@()
    }
  }
  return Resolve-PublicDemoOwnedProcessTree -Snapshot @($Live.processes) `
    -RootPid ([int]$identity.pid) `
    -RootCreationTimeUtc ([string]$identity.creation_time_utc) `
    -SnapshotTimeUtc ([string]$Live.captured_at_utc)
}

function ConvertTo-StateIdentity($Identity) {
  return [ordered]@{
    pid = [int]$Identity.pid
    creation_time_utc = [string]$Identity.creation_time_utc
    creation_time = [string]$Identity.creation_time_utc
    parent_pid = [int]$Identity.parent_pid
    process_name = [string]$Identity.process_name
    executable = [string]$Identity.executable_path
    executable_path = [string]$Identity.executable_path
    command_line_hash = [string]$Identity.command_line_hash
  }
}

function Get-CanonicalTree([int] $RootPid) {
  $liveNow = Get-PublicDemoLiveProcessSnapshot
  $root = @($liveNow.processes | Where-Object { [int]$_.process_id -eq $RootPid })
  if ($root.Count -ne 1) { throw "Process root $RootPid is not uniquely present in CIM." }
  $resolved = Resolve-PublicDemoOwnedProcessTree -Snapshot @($liveNow.processes) `
    -RootPid $RootPid -RootCreationTimeUtc ([string]$root[0].creation_time_utc) `
    -SnapshotTimeUtc ([string]$liveNow.captured_at_utc)
  if (-not $resolved.root_trusted) { throw "Process root $RootPid is not trusted." }
  return @($resolved.accepted_tree | ForEach-Object {
    $item = ConvertTo-StateIdentity $_
    $item.depth = [int]$_.depth
    $item.killable = [bool]$_.killable
    [pscustomobject]$item
  })
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

function Write-StateAtomically {
  $temporaryState = "$StatePath.update-$([Guid]::NewGuid().ToString('N')).tmp"
  try {
    $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporaryState -Encoding utf8
    $null = Get-Content -LiteralPath $temporaryState -Raw | ConvertFrom-Json -DateKind String
    Move-Item -LiteralPath $temporaryState -Destination $StatePath -Force
  } finally {
    if (Test-Path -LiteralPath $temporaryState) { Remove-Item -LiteralPath $temporaryState -Force }
  }
}

$componentName = $Component.ToLowerInvariant()
$live = Get-PublicDemoLiveProcessSnapshot
$components = [ordered]@{}
foreach ($name in @('api','worker','cloudflared')) {
  $components[$name] = Resolve-StoredComponent $name $live
}
$disjoint = Test-PublicDemoOwnershipDisjoint $components
if (-not $disjoint.disjoint) { throw 'COMPONENT_OWNERSHIP_SET_OVERLAP' }
$targetResult = $components[$componentName]
$targets = @($targetResult.accepted_tree | Where-Object { $_.killable } |
  Sort-Object -Property @{ Expression={ [int]$_.depth }; Descending=$true })

if ($DryRun) {
  if (-not $targetResult.root_trusted) { throw "${Component}_OWNERSHIP_NOT_TRUSTED" }
  [ordered]@{
    mode='DRY_RUN'; component=$Component; targets=$targets
    ownership_disjointness=$disjoint.classification; processes_terminated=0
  } | ConvertTo-Json -Depth 8 | Write-Output
  exit 0
}
if ($StopOnly -and -not $targetResult.root_trusted) {
  throw "${Component}_OWNERSHIP_NOT_TRUSTED"
}

foreach ($identity in $targets) {
  $current = Get-PublicDemoLiveProcessSnapshot
  $match = Test-PublicDemoProcessIdentity $identity @($current.processes)
  if ($match.matched) { & taskkill.exe /PID ([int]$identity.pid) /F 2>$null | Out-Null }
}
$deadline = (Get-Date).AddSeconds(15)
do {
  $current = Get-PublicDemoLiveProcessSnapshot
  $survivors = @($targets | Where-Object {
    (Test-PublicDemoProcessIdentity $_ @($current.processes)).matched
  })
  if ($survivors.Count -eq 0) { break }
  Start-Sleep -Milliseconds 200
} while ((Get-Date) -lt $deadline)
if ($survivors.Count -ne 0) { throw "Owned $Component processes did not exit." }

$apiPort = [int]$state.api_port
if ($Component -eq 'Api' -and $targetResult.root_trusted) {
  $deadline = (Get-Date).AddSeconds(10)
  while ((Get-Date) -lt $deadline -and (Test-PortInUse $apiPort)) {
    Start-Sleep -Milliseconds 200
  }
  if (Test-PortInUse $apiPort) { throw "API port $apiPort was not released." }
}
if ($StopOnly) {
  $state | Add-Member -NotePropertyName "${componentName}_status" -NotePropertyValue 'OFFLINE' -Force
  Write-StateAtomically
  Write-Output "PUBLIC_DEMO_${($Component.ToUpperInvariant())}_STOP=PASS"
  exit 0
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
} elseif ($Component -eq 'Worker') {
  $started = Start-Process -FilePath $PythonPath `
    -ArgumentList '-m','services.worker.main','--poll-seconds','2' `
    -WorkingDirectory $project -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs 'worker.log') `
    -RedirectStandardError (Join-Path $logs 'worker-error.log')
  Start-Sleep -Milliseconds 500
  if ($started.HasExited) { throw 'Worker exited during restart.' }
} else {
  $cloudflaredPath = if ($state.cloudflared_path) {
    [string]$state.cloudflared_path
  } else {
    [string]$state.cloudflared_process.executable_path
  }
  if (-not (Test-Path -LiteralPath $cloudflaredPath -PathType Leaf)) {
    throw "cloudflared executable not found: $cloudflaredPath"
  }
  $prefix = if ($state.cloudflared_argument_prefix) { @($state.cloudflared_argument_prefix) } else { @() }
  $arguments = @($prefix) + @('tunnel','--url',"http://127.0.0.1:$apiPort")
  $started = Start-Process -FilePath $cloudflaredPath -ArgumentList $arguments `
    -WorkingDirectory $project -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs 'cloudflared-stdout.log') `
    -RedirectStandardError (Join-Path $logs 'cloudflared.log')
  $tunnelUrl = $null
  $deadline = (Get-Date).AddSeconds(45)
  while (-not $tunnelUrl -and (Get-Date) -lt $deadline) {
    if ($started.HasExited) { throw 'cloudflared exited before publishing a tunnel URL.' }
    $match = Select-String -Path (Join-Path $logs 'cloudflared.log') `
      -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue |
      Select-Object -First 1
    if ($match) { $tunnelUrl = $match.Matches[0].Value }
    if (-not $tunnelUrl) { Start-Sleep -Milliseconds 250 }
  }
  if (-not $tunnelUrl) { throw 'Quick Tunnel URL was not observed during restart.' }
  $state.tunnel_origin = $tunnelUrl
  $state.share_url = "$vercelOrigin/?rn_backend=$([uri]::EscapeDataString($tunnelUrl))"
}

$tree = @(Get-CanonicalTree $started.Id)
$state."${componentName}_pid" = $started.Id
$state."${componentName}_process" = [pscustomobject](ConvertTo-StateIdentity $tree[0])
$state."${componentName}_process_tree" = $tree
$state | Add-Member -NotePropertyName "${componentName}_status" -NotePropertyValue 'ONLINE' -Force
Write-StateAtomically
Add-Content -LiteralPath (Join-Path $logs 'deployment.log') -Value (
  "$(Get-Date -Format o) RESTARTED component=$Component pid=$($started.Id)"
)
Write-Output "PUBLIC_DEMO_${($Component.ToUpperInvariant())}_RESTART=PASS"
