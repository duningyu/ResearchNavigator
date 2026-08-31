[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [string] $StatePath,
  [string] $PythonPath,
  [switch] $EmitJson,
  [string] $OutputPath,
  [switch] $SkipExternalChecks
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $ProjectRoot).Path
$guard = Join-Path $PSScriptRoot 'assert_researchnavigator_context.ps1'
& $guard -ProjectRoot $project -Quiet
if ($LASTEXITCODE -ne 0) { throw 'ResearchNavigator execution context guard refused status.' }
Import-Module (Join-Path $PSScriptRoot 'PublicDemoProcessOwnership.psm1') -Force
if (-not $StatePath) { $StatePath = Join-Path $project 'deployment/public_demo_state.json' }
if (-not $OutputPath) { $OutputPath = Join-Path $project 'deployment/public_demo_status.json' }
if (-not $PythonPath) { $PythonPath = Join-Path $project '.venv/Scripts/python.exe' }

function Test-Http([string] $Url) {
  try {
    $response = Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) { return 'ONLINE' }
    return "HTTP_$($response.StatusCode)"
  } catch { return 'OFFLINE' }
}

if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
  $receipt = [ordered]@{
    status = 'OFFLINE'
    checked_at = (Get-Date).ToUniversalTime().ToString('o')
    components = [ordered]@{
      vercel = $(if ($SkipExternalChecks) { 'NOT_CHECKED' } else { 'UNKNOWN' })
      local_api = 'OFFLINE'
      worker = 'OFFLINE'
      cloudflared = 'OFFLINE'
      public_api = 'OFFLINE'
    }
    database = $null
    tunnel_url = $null
    share_url = $null
    started_at = $null
  }
} else {
  $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json -DateKind String
  $live = Get-PublicDemoLiveProcessSnapshot
  $apiIdentity = Test-PublicDemoProcessIdentity $state.api_process @($live.processes)
  $workerIdentity = Test-PublicDemoProcessIdentity $state.worker_process @($live.processes)
  $tunnelIdentity = Test-PublicDemoProcessIdentity $state.cloudflared_process @($live.processes)
  $apiHealth = Test-Http "http://127.0.0.1:$($state.api_port)/api/health"
  $localApi = $(if ($apiIdentity.matched) { $apiHealth } else { 'OFFLINE' })
  $worker = $(if ($workerIdentity.matched) { 'ONLINE' } else { 'OFFLINE' })
  $cloudflared = $(
    if ($tunnelIdentity.matched) { 'ONLINE' } else { 'OFFLINE' }
  )
  if ($SkipExternalChecks) {
    $vercel = 'NOT_CHECKED'
    $publicApi = 'NOT_CHECKED'
  } else {
    $vercel = Test-Http ([string]$state.vercel_origin)
    $publicApi = Test-Http "$($state.tunnel_origin)/api/health"
  }
  $database = $null
  if (Test-Path -LiteralPath $PythonPath -PathType Leaf) {
    $databaseJson = & $PythonPath (Join-Path $project 'scripts/deployment/inspect_public_demo.py') `
      --data-dir ([string]$state.demo_data_dir)
    if ($LASTEXITCODE -eq 0) { $database = $databaseJson | ConvertFrom-Json }
  }
  $onlineLocal = $localApi -eq 'ONLINE' -and $worker -eq 'ONLINE' -and $cloudflared -eq 'ONLINE'
  $allOnline = $onlineLocal -and $vercel -eq 'ONLINE' -and $publicApi -eq 'ONLINE'
  $overall = $(if ($allOnline) { 'ONLINE' } elseif ($onlineLocal) { 'DEGRADED' } else { 'OFFLINE' })
  $receipt = [ordered]@{
    status = $overall
    checked_at = (Get-Date).ToUniversalTime().ToString('o')
    components = [ordered]@{
      vercel = $vercel
      local_api = $localApi
      worker = $worker
      cloudflared = $cloudflared
      public_api = $publicApi
    }
    database = $database
    tunnel_url = $state.tunnel_origin
    share_url = $state.share_url
    started_at = $state.started_at
    api_pid = $state.api_pid
    worker_pid = $state.worker_pid
    cloudflared_pid = $state.cloudflared_pid
  }
}

$json = $receipt | ConvertTo-Json -Depth 6
if ($EmitJson) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null
  $json | Set-Content -LiteralPath $OutputPath -Encoding utf8
}
Write-Output $json
