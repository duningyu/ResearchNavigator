[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [Parameter(Mandatory)] [uri] $VercelOrigin,
  [int] $ApiPort = 8000,
  [Parameter(Mandatory)] [string] $DemoDataDir,
  [string] $StatePath,
  [string] $CloudflaredPath,
  [string[]] $CloudflaredArgumentPrefix = @(),
  [string] $PythonPath
)

$ErrorActionPreference = 'Stop'
$markerKind = 'RESEARCH_NAVIGATOR_PUBLIC_DEMO_RUNTIME_V1'
$project = (Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd('\')
$demo = [IO.Path]::GetFullPath($DemoDataDir).TrimEnd('\')
if (-not $StatePath) { $StatePath = Join-Path $project 'deployment/public_demo_state.json' }
$StatePath = [IO.Path]::GetFullPath($StatePath)
if (-not ($VercelOrigin.Scheme -eq 'https' -and $VercelOrigin.AbsolutePath -eq '/')) {
  throw 'VercelOrigin must be an HTTPS origin.'
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

function Test-OwnedIdentity($Identity) {
  if (-not $Identity -or -not $Identity.pid -or -not $Identity.creation_time) { return $false }
  $process = Get-Process -Id ([int]$Identity.pid) -ErrorAction SilentlyContinue
  if (-not $process) { return $false }
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
    $actual = $process.StartTime.ToUniversalTime()
    if ([Math]::Abs(($actual - $expected).TotalSeconds) -ge 1) { return $false }
    if ($Identity.executable) {
      try {
        if (-not $process.Path.Equals(
          [string]$Identity.executable, [StringComparison]::OrdinalIgnoreCase
        )) { return $false }
      } catch { return $false }
    }
    return $true
  } catch { return $false }
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

function Test-LocalHealth([int] $Port) {
  try {
    $response = Invoke-WebRequest "http://127.0.0.1:$Port/api/health" `
      -UseBasicParsing -TimeoutSec 3
    return $response.StatusCode -eq 200
  } catch { return $false }
}

function Test-PortInUse([int] $Port) {
  $client = [Net.Sockets.TcpClient]::new()
  try {
    $task = $client.ConnectAsync('127.0.0.1', $Port)
    return $task.Wait(500) -and $client.Connected
  } catch { return $false } finally { $client.Dispose() }
}

if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
  $existing = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
  $apiOwned = Test-OwnedIdentity $existing.api_process
  $workerOwned = Test-OwnedIdentity $existing.worker_process
  $tunnelOwned = Test-OwnedIdentity $existing.cloudflared_process
  $localHealthy = Test-LocalHealth ([int]$existing.api_port)
  $diagnosticLog = Join-Path ([string]$existing.demo_data_dir) 'logs/deployment.log'
  if (Test-Path -LiteralPath (Split-Path -Parent $diagnosticLog)) {
    Add-Content -LiteralPath $diagnosticLog -Value (
      "$(Get-Date -Format o) IDEMPOTENCY api=$apiOwned worker=$workerOwned " +
      "tunnel=$tunnelOwned health=$localHealthy"
    )
  }
  if ($apiOwned -and $workerOwned -and $tunnelOwned -and $localHealthy) {
    Write-Output $existing.share_url
    exit 0
  }
  & (Join-Path $project 'scripts/deployment/stop_public_demo.ps1') `
    -ProjectRoot $project -StatePath $StatePath
}

$driveRoot = [IO.Path]::GetPathRoot($demo).TrimEnd('\')
$userHome = [Environment]::GetFolderPath('UserProfile').TrimEnd('\')
if ($demo.Equals($driveRoot, [StringComparison]::OrdinalIgnoreCase)) {
  throw 'DemoDataDir must not be a drive root.'
}
if ($demo.Equals($userHome, [StringComparison]::OrdinalIgnoreCase)) {
  throw 'DemoDataDir must not be the user home directory.'
}
if (
  $demo.Equals($project, [StringComparison]::OrdinalIgnoreCase) -or
  $demo.StartsWith("$project\", [StringComparison]::OrdinalIgnoreCase) -or
  $project.StartsWith("$demo\", [StringComparison]::OrdinalIgnoreCase)
) { throw 'DemoDataDir must be isolated from the repository.' }

if (-not (Test-Path -LiteralPath $demo)) { New-Item -ItemType Directory -Path $demo | Out-Null }
$markerPath = Join-Path $demo 'PUBLIC_DEMO_RUNTIME.marker'
if (-not (Test-Path -LiteralPath $markerPath)) {
  if (@(Get-ChildItem -LiteralPath $demo -Force).Count -ne 0) {
    throw 'Refusing to initialize a non-empty unmarked DemoDataDir.'
  }
  [ordered]@{
    marker = $markerKind
    project_root = $project
    created_at = (Get-Date).ToUniversalTime().ToString('o')
  } | ConvertTo-Json | Set-Content -LiteralPath $markerPath -Encoding utf8
}
$marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
if ($marker.marker -ne $markerKind) { throw 'DemoDataDir marker is invalid.' }
$markerProject = [IO.Path]::GetFullPath([string]$marker.project_root).TrimEnd('\')
if (-not $markerProject.Equals($project, [StringComparison]::OrdinalIgnoreCase)) {
  throw 'DemoDataDir marker belongs to another repository.'
}

if (-not $PythonPath) { $PythonPath = Join-Path $project '.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
  throw "Python environment not found: $PythonPath"
}
$pythonVersion = (& $PythonPath -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")').Trim()
if ($LASTEXITCODE -ne 0 -or [Version]$pythonVersion -lt [Version]'3.12') {
  throw 'Python 3.12 or newer is required.'
}
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCommand) {
  & $uvCommand.Source --version | Out-Null
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  & py -3.12 -m uv --version | Out-Null
} else {
  throw 'uv is required.'
}
if ($LASTEXITCODE -ne 0) { throw 'uv preflight failed.' }
if (-not $CloudflaredPath) {
  $cloudflaredCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
  if (-not $cloudflaredCommand) { throw 'cloudflared is required.' }
  $CloudflaredPath = $cloudflaredCommand.Source
}
if (-not (Test-Path -LiteralPath $CloudflaredPath -PathType Leaf)) {
  throw "cloudflared executable not found: $CloudflaredPath"
}
if (Test-PortInUse $ApiPort) { throw "API port $ApiPort is already in use." }

$logs = Join-Path $demo 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$databasePath = Join-Path $demo 'research_navigator.db'
if (-not (Test-Path -LiteralPath $databasePath)) {
  & (Join-Path $project 'scripts/deployment/reset_public_demo.ps1') `
    -ProjectRoot $project -DemoDataDir $demo -StatePath $StatePath -PythonPath $PythonPath
}

$databaseUrlPath = $databasePath.Replace('\', '/')
$vercelOriginText = $VercelOrigin.AbsoluteUri.TrimEnd('/')
$env:RN_DATA_DIR = $demo
$env:RN_DATABASE_URL = "sqlite+pysqlite:///$databaseUrlPath"
$env:RN_UPLOAD_DIR = Join-Path $demo 'uploads'
$env:RN_VECTOR_DIR = Join-Path $demo 'vector_index'
$env:RN_BACKUP_DIR = Join-Path $demo 'backups'
$env:RN_CORS_ALLOWED_ORIGINS = $vercelOriginText
$env:RN_ALLOWED_ORIGINS = $vercelOriginText
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

$api = $null
$worker = $null
$tunnel = $null
Push-Location $project
try {
  & $PythonPath -m alembic upgrade head *>> (Join-Path $logs 'deployment.log')
  if ($LASTEXITCODE -ne 0) { throw 'Alembic migration failed.' }
  $api = Start-Process -FilePath $PythonPath `
    -ArgumentList '-m','uvicorn','research_navigator.main:app','--host','127.0.0.1','--port',"$ApiPort" `
    -WorkingDirectory $project -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs 'api.log') `
    -RedirectStandardError (Join-Path $logs 'api-error.log')
  $worker = Start-Process -FilePath $PythonPath `
    -ArgumentList '-m','services.worker.main','--poll-seconds','2' `
    -WorkingDirectory $project -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs 'worker.log') `
    -RedirectStandardError (Join-Path $logs 'worker-error.log')
  $deadline = (Get-Date).AddSeconds(45)
  while ((Get-Date) -lt $deadline -and -not (Test-LocalHealth $ApiPort)) {
    if ($api.HasExited) { throw 'API exited before readiness.' }
    if ($worker.HasExited) { throw 'Worker exited before API readiness.' }
    Start-Sleep -Milliseconds 250
  }
  if (-not (Test-LocalHealth $ApiPort)) { throw 'Local API health did not become ready.' }
  $cloudflaredArguments = @($CloudflaredArgumentPrefix) + @(
    'tunnel', '--url', "http://127.0.0.1:$ApiPort"
  )
  $tunnel = Start-Process -FilePath $CloudflaredPath `
    -ArgumentList $cloudflaredArguments `
    -WorkingDirectory $project -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs 'cloudflared-stdout.log') `
    -RedirectStandardError (Join-Path $logs 'cloudflared.log')
  $tunnelUrl = $null
  $deadline = (Get-Date).AddSeconds(45)
  while (-not $tunnelUrl -and (Get-Date) -lt $deadline) {
    if ($tunnel.HasExited) { throw 'cloudflared exited before publishing a tunnel URL.' }
    if (Test-Path -LiteralPath (Join-Path $logs 'cloudflared.log')) {
      $match = Select-String -Path (Join-Path $logs 'cloudflared.log') `
        -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
      if ($match) { $tunnelUrl = $match.Matches[0].Value }
    }
    if (-not $tunnelUrl) { Start-Sleep -Milliseconds 250 }
  }
  if (-not $tunnelUrl) { throw 'Quick Tunnel URL was not observed.' }
  $shareUrl = "$vercelOriginText/?rn_backend=$([uri]::EscapeDataString($tunnelUrl))"
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $StatePath) | Out-Null
  $state = [ordered]@{
    version = '2.2.3'
    source_commit = (& git rev-parse HEAD).Trim()
    deployment_revision = 'RN223_PUBLIC_DEMO_HARDENING_V1'
    vercel_origin = $vercelOriginText
    tunnel_origin = $tunnelUrl
    api_port = $ApiPort
    api_pid = $api.Id
    worker_pid = $worker.Id
    cloudflared_pid = $tunnel.Id
    api_process = Get-ProcessIdentity $api
    worker_process = Get-ProcessIdentity $worker
    cloudflared_process = Get-ProcessIdentity $tunnel
    api_process_tree = @(Get-OwnedProcessTree $api.Id)
    worker_process_tree = @(Get-OwnedProcessTree $worker.Id)
    cloudflared_process_tree = @(Get-OwnedProcessTree $tunnel.Id)
    demo_data_dir = $demo
    share_url = $shareUrl
    started_at = (Get-Date).ToUniversalTime().ToString('o')
    cloudflare_tunnel_type = 'QUICK_TUNNEL'
    random_hostname = $true
    sla = 'none'
  }
  $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StatePath -Encoding utf8
  Add-Content -LiteralPath (Join-Path $logs 'deployment.log') `
    -Value "$(Get-Date -Format o) STARTED api=$($api.Id) worker=$($worker.Id) tunnel=$($tunnel.Id)"
  Write-Output $shareUrl
} catch {
  foreach ($process in @($tunnel, $worker, $api)) {
    if ($process -and -not $process.HasExited) {
      & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
    }
  }
  throw
} finally { Pop-Location }
