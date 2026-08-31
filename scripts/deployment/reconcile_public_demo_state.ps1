[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [string] $StatePath,
  [string] $ForensicsDir,
  [switch] $PreviewOnly
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd('\')
if (-not $StatePath) { $StatePath = Join-Path $project 'deployment/public_demo_state.json' }
$StatePath = [IO.Path]::GetFullPath($StatePath)
if (-not $ForensicsDir) { $ForensicsDir = Join-Path $project 'deployment/ownership_forensics' }
$ForensicsDir = [IO.Path]::GetFullPath($ForensicsDir)
if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
  throw "Public demo state not found: $StatePath"
}
New-Item -ItemType Directory -Force -Path $ForensicsDir | Out-Null
Import-Module (Join-Path $PSScriptRoot 'PublicDemoProcessOwnership.psm1') -Force

$state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json -DateKind String
$live = Get-PublicDemoLiveProcessSnapshot
$snapshot = @($live.processes)
$capturedAt = ConvertTo-PublicDemoUtcTimestamp $live.captured_at_utc
$startedAt = ConvertTo-PublicDemoUtcTimestamp ([string]$state.started_at)
$startWindow = $startedAt.AddMinutes(-2)

function Get-Created($Record) {
  return ConvertTo-PublicDemoUtcTimestamp ([string]$Record.creation_time_utc)
}

function Get-RootCandidates([string] $CommandPattern, [string] $NamePattern) {
  $matching = @($snapshot | Where-Object {
    ([string]$_.name) -match $NamePattern -and
    ([string]$_.command_line) -match $CommandPattern -and
    (Get-Created $_) -ge $startWindow -and
    (Get-Created $_) -le $capturedAt
  })
  $matchingPids = @($matching | ForEach-Object { [int]$_.process_id })
  return @($matching | Where-Object { [int]$_.parent_process_id -notin $matchingPids })
}

$apiListeners = @(Get-NetTCPConnection -State Listen -LocalPort ([int]$state.api_port) `
  -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
if ($apiListeners.Count -ne 1) { throw 'API_OWNERSHIP_RECONCILIATION_AMBIGUOUS' }
$apiRoots = @(Get-RootCandidates '-m\s+uvicorn\s+research_navigator\.main:app' 'python(\.exe)?$')
$apiMatches = @()
foreach ($candidate in $apiRoots) {
  $resolved = Resolve-PublicDemoOwnedProcessTree -Snapshot $snapshot `
    -RootPid ([int]$candidate.process_id) `
    -RootCreationTimeUtc ([string]$candidate.creation_time_utc) `
    -SnapshotTimeUtc $live.captured_at_utc
  if ($resolved.root_trusted -and [int]$apiListeners[0] -in @($resolved.accepted_tree.pid)) {
    $apiMatches += [pscustomobject]@{ root=$candidate; resolution=$resolved }
  }
}
if ($apiMatches.Count -ne 1) { throw 'API_OWNERSHIP_RECONCILIATION_AMBIGUOUS' }

$workerRoots = @(Get-RootCandidates '-m\s+services\.worker\.main(?:\s|$)' 'python(\.exe)?$')
if ($workerRoots.Count -ne 1) { throw 'WORKER_OWNERSHIP_RECONCILIATION_AMBIGUOUS' }
$workerResolution = Resolve-PublicDemoOwnedProcessTree -Snapshot $snapshot `
  -RootPid ([int]$workerRoots[0].process_id) `
  -RootCreationTimeUtc ([string]$workerRoots[0].creation_time_utc) `
  -SnapshotTimeUtc $live.captured_at_utc
if (-not $workerResolution.root_trusted) { throw 'WORKER_OWNERSHIP_RECONCILIATION_AMBIGUOUS' }

$portPattern = [Regex]::Escape("http://127.0.0.1:$([int]$state.api_port)")
$tunnelRoots = @(Get-RootCandidates "tunnel.*$portPattern" '^cloudflared\.exe$')
if ($tunnelRoots.Count -ne 1) { throw 'CLOUDFLARED_OWNERSHIP_RECONCILIATION_AMBIGUOUS' }
$tunnelResolution = Resolve-PublicDemoOwnedProcessTree -Snapshot $snapshot `
  -RootPid ([int]$tunnelRoots[0].process_id) `
  -RootCreationTimeUtc ([string]$tunnelRoots[0].creation_time_utc) `
  -SnapshotTimeUtc $live.captured_at_utc
if (-not $tunnelResolution.root_trusted) { throw 'CLOUDFLARED_OWNERSHIP_RECONCILIATION_AMBIGUOUS' }

$components = [ordered]@{
  api = $apiMatches[0].resolution
  worker = $workerResolution
  cloudflared = $tunnelResolution
}
$disjoint = Test-PublicDemoOwnershipDisjoint $components
if (-not $disjoint.disjoint) { throw 'COMPONENT_OWNERSHIP_SET_OVERLAP' }

$preview = [ordered]@{
  generated_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
  mode = if ($PreviewOnly) { 'PREVIEW_ONLY' } else { 'RECONCILIATION' }
  api_listener_pid = [int]$apiListeners[0]
  components = $components
  ownership_disjointness = $disjoint
}
$previewPath = Join-Path $ForensicsDir 'RECONCILIATION_PREVIEW.json'
$preview | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $previewPath -Encoding utf8
if ($PreviewOnly) {
  Write-Output ($preview | ConvertTo-Json -Depth 10)
  exit 0
}

$beforePath = Join-Path $ForensicsDir 'PUBLIC_DEMO_STATE_PRE_RECONCILIATION.json'
if (Test-Path -LiteralPath $beforePath) {
  throw "Refusing to overwrite reconciliation evidence: $beforePath"
}
Copy-Item -LiteralPath $StatePath -Destination $beforePath
$beforeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $beforePath).Hash.ToLowerInvariant()

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

foreach ($name in @('api','worker','cloudflared')) {
  $tree = @($components[$name].accepted_tree | ForEach-Object {
    $item = ConvertTo-StateIdentity $_
    $item.depth = [int]$_.depth
    $item.killable = [bool]$_.killable
    [pscustomobject]$item
  })
  $rootIdentity = ConvertTo-StateIdentity $tree[0]
  $state."${name}_pid" = [int]$tree[0].pid
  $state."${name}_process" = [pscustomobject]$rootIdentity
  $state."${name}_process_tree" = $tree
}

$temporaryState = "$StatePath.reconcile-$([Guid]::NewGuid().ToString('N')).tmp"
try {
  $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporaryState -Encoding utf8
  $null = Get-Content -LiteralPath $temporaryState -Raw | ConvertFrom-Json -DateKind String
  Move-Item -LiteralPath $temporaryState -Destination $StatePath -Force
} finally {
  if (Test-Path -LiteralPath $temporaryState) { Remove-Item -LiteralPath $temporaryState -Force }
}
$afterHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $StatePath).Hash.ToLowerInvariant()
$receipt = [ordered]@{
  bug_id = 'RN223-DEMO-PROC-OWNERSHIP-001'
  reconciled_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
  before_state_sha256 = $beforeHash
  after_state_sha256 = $afterHash
  api_root_identity = $state.api_process
  worker_root_identity = $state.worker_process
  cloudflared_root_identity = $state.cloudflared_process
  accepted_descendant_count = [ordered]@{
    api = [Math]::Max(0, @($state.api_process_tree).Count - 1)
    worker = [Math]::Max(0, @($state.worker_process_tree).Count - 1)
    cloudflared = [Math]::Max(0, @($state.cloudflared_process_tree).Count - 1)
  }
  rejected_impossible_edge_count = @(
    $components.Values.rejected_edges | Where-Object reason -eq 'IMPOSSIBLE_CAUSAL_PARENT_EDGE'
  ).Count
  pid_reuse_detections = @($components.Values | Where-Object classification -eq 'PID_REUSED').Count
  ownership_disjointness = $disjoint.classification
  processes_terminated = 0
}
$receipt | ConvertTo-Json -Depth 8 | Set-Content `
  -LiteralPath (Join-Path $ForensicsDir 'OWNERSHIP_STATE_RECONCILIATION_RECEIPT.json') -Encoding utf8
Write-Output ($receipt | ConvertTo-Json -Depth 8)
