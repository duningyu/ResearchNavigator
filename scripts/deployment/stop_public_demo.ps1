[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [string] $StatePath,
  [switch] $DryRun
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $ProjectRoot).Path
Import-Module (Join-Path $PSScriptRoot 'PublicDemoProcessOwnership.psm1') -Force
if (-not $StatePath) { $StatePath = Join-Path $project 'deployment/public_demo_state.json' }
$StatePath = [IO.Path]::GetFullPath($StatePath)
if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
  Write-Output 'No public demo state found.'
  exit 0
}
$state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json -DateKind String
$diagnosticLog = if ($state.demo_data_dir) {
  Join-Path ([string]$state.demo_data_dir) 'logs/deployment.log'
} else { $null }

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

$live = Get-PublicDemoLiveProcessSnapshot
$components = [ordered]@{}
foreach ($name in @('api','worker','cloudflared')) {
  $components[$name] = Resolve-StoredComponent $name $live
}
$disjoint = Test-PublicDemoOwnershipDisjoint $components
if (-not $disjoint.disjoint) { throw 'COMPONENT_OWNERSHIP_SET_OVERLAP' }
$targets = @($components.Values.accepted_tree | Where-Object { $_.killable } |
  Sort-Object -Property @{ Expression={ [int]$_.depth }; Descending=$true })
if ($DryRun) {
  [ordered]@{
    mode='DRY_RUN'; component='ALL'; targets=$targets
    ownership_disjointness=$disjoint.classification; processes_terminated=0
  } | ConvertTo-Json -Depth 8 | Write-Output
  exit 0
}

foreach ($identity in $targets) {
  $current = Get-PublicDemoLiveProcessSnapshot
  $match = Test-PublicDemoProcessIdentity $identity @($current.processes)
  if ($diagnosticLog -and (Test-Path -LiteralPath (Split-Path -Parent $diagnosticLog))) {
    Add-Content -LiteralPath $diagnosticLog -Value (
      "$(Get-Date -Format o) STOP_MATCH pid=$($identity.pid) depth=$($identity.depth) " +
      "classification=$($match.classification)"
    )
  }
  if ($match.matched) {
    & taskkill.exe /PID ([int]$identity.pid) /F 2>$null | Out-Null
  }
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
  if ($portInUse) { throw "API port $($state.api_port) remains in use after stop." }
}

if ($diagnosticLog -and (Test-Path -LiteralPath (Split-Path -Parent $diagnosticLog))) {
  Add-Content -LiteralPath $diagnosticLog -Value "$(Get-Date -Format o) STOPPED"
}
Remove-Item -LiteralPath $StatePath -Force
Write-Output 'PUBLIC_DEMO_STOP=PASS'
