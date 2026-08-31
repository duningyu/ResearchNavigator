[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [string] $StatePath
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $ProjectRoot).Path
if (-not $StatePath) { $StatePath = Join-Path $project 'deployment/public_demo_state.json' }
$StatePath = [IO.Path]::GetFullPath($StatePath)
if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
  Write-Output 'No public demo state found.'
  exit 0
}
$state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
$diagnosticLog = $null
if ($state.demo_data_dir) {
  $diagnosticLog = Join-Path ([string]$state.demo_data_dir) 'logs/deployment.log'
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
    $actual = $process.StartTime.ToUniversalTime()
    if ([Math]::Abs(($actual - $expected).TotalSeconds) -ge 1) { return $null }
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

$owned = @()
$owned += @($state.cloudflared_process_tree)
$owned += @($state.worker_process_tree)
$owned += @($state.api_process_tree)
$owned = @($owned | Where-Object { $_ -and $_.pid })
if ($owned.Count -eq 0) {
  $owned = @($state.cloudflared_process, $state.worker_process, $state.api_process)
}
$owned = @($owned | Sort-Object -Property @{ Expression = { [int]$_.depth }; Descending = $true })
foreach ($identity in $owned) {
  $process = Get-MatchingProcess $identity
  if ($diagnosticLog) {
    Add-Content -LiteralPath $diagnosticLog -Value (
      "$(Get-Date -Format o) STOP_MATCH pid=$($identity.pid) depth=$($identity.depth) " +
      "matched=$([bool]$process)"
    )
  }
  if ($process) {
    & taskkill.exe /PID $process.Id /F 2>$null | Out-Null
    if ($diagnosticLog) {
      Add-Content -LiteralPath $diagnosticLog -Value (
        "$(Get-Date -Format o) STOP_TASKKILL pid=$($process.Id) exit=$LASTEXITCODE"
      )
    }
  }
}

$deadline = (Get-Date).AddSeconds(15)
do {
  $survivors = @($owned | Where-Object { Get-MatchingProcess $_ })
  if ($survivors.Count -eq 0) { break }
  Start-Sleep -Milliseconds 200
} while ((Get-Date) -lt $deadline)
if ($survivors.Count -ne 0) { throw 'One or more owned public demo processes did not exit.' }

if ($state.api_port) {
  $portDeadline = (Get-Date).AddSeconds(10)
  do {
    $client = [Net.Sockets.TcpClient]::new()
    try {
      $task = $client.ConnectAsync('127.0.0.1', [int]$state.api_port)
      $portInUse = $task.Wait(300) -and $client.Connected
    } catch { $portInUse = $false } finally { $client.Dispose() }
    if (-not $portInUse) { break }
    Start-Sleep -Milliseconds 200
  } while ((Get-Date) -lt $portDeadline)
  if ($portInUse) {
    $owner = Get-NetTCPConnection -LocalPort ([int]$state.api_port) -State Listen `
      -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess
    if ($diagnosticLog) {
      Add-Content -LiteralPath $diagnosticLog -Value (
        "$(Get-Date -Format o) STOP_PORT_REMAINS port=$($state.api_port) owner=$owner"
      )
    }
    throw "API port $($state.api_port) remains in use after stop."
  }
}

if ($state.demo_data_dir) {
  $logPath = Join-Path ([string]$state.demo_data_dir) 'logs/deployment.log'
  if (Test-Path -LiteralPath (Split-Path -Parent $logPath)) {
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format o) STOPPED"
  }
}
Remove-Item -LiteralPath $StatePath -Force
Write-Output 'PUBLIC_DEMO_STOP=PASS'
