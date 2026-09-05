[CmdletBinding(DefaultParameterSetName='Audit')]
param(
  [Parameter(ParameterSetName='Audit', Mandatory=$true)] [switch] $Audit,
  [Parameter(ParameterSetName='DryRun', Mandatory=$true)] [switch] $DryRun,
  [Parameter(ParameterSetName='Execute', Mandatory=$true)] [switch] $Execute,
  [Parameter(ParameterSetName='Verify', Mandatory=$true)] [switch] $Verify,
  [Parameter(ParameterSetName='DryRun', Mandatory=$true)]
  [Parameter(ParameterSetName='Execute', Mandatory=$true)]
  [Parameter(ParameterSetName='Verify', Mandatory=$true)] [string] $Manifest,
  [Parameter(ParameterSetName='Execute', Mandatory=$true)] [string] $ManifestSha256
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
& (Join-Path $root 'scripts/deployment/assert_researchnavigator_context.ps1') -ProjectRoot $root -Quiet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$mode = if ($Audit) { 'audit' } elseif ($DryRun) { 'dry-run' } elseif ($Execute) { 'execute' } else { 'verify' }
$controller = Join-Path $root 'deployment/cloud/acceptance/preview_fixture_controller.py'
$dockerImage = 'rn223-schema-audit:py312-libsql020'
$pythonInImage = 'python'
$rootFull = ([IO.Path]::GetFullPath($root)).TrimEnd('\') + '\'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw 'Docker is required for the verified Python/libsql acceptance runtime.'
}

if ($Audit) {
  $auditDockerArgs = @(
    'run', '--rm', '--network', 'none',
    '--mount', "type=bind,source=$root,target=/workspace,readonly",
    '--workdir', '/workspace',
    $dockerImage,
    $pythonInImage, '/workspace/deployment/cloud/acceptance/preview_fixture_controller.py', 'audit'
  )
  & docker @auditDockerArgs
  exit $LASTEXITCODE
}

$manifestPath = ([IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Manifest).Path))
if (-not $manifestPath.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
  throw 'Manifest must be inside the ResearchNavigator worktree.'
}
$manifestObject = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json

function Read-HiddenValue([string] $Prompt) {
  $secure = Read-Host -Prompt $Prompt -AsSecureString
  $ptr = [IntPtr]::Zero
  try {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  }
  finally {
    if ($ptr -ne [IntPtr]::Zero) {
      [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    $secure.Dispose()
  }
}

$envNames = @(
  'DATABASE_BACKEND', 'RN223_TARGET_DATABASE', 'TURSO_DATABASE_URL', 'TURSO_AUTH_TOKEN',
  'R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET', 'R2_ENDPOINT'
)
$oldEnv = @{}
foreach ($name in $envNames) { $oldEnv[$name] = [Environment]::GetEnvironmentVariable($name) }

try {
  $env:DATABASE_BACKEND = 'turso'
  $env:RN223_TARGET_DATABASE = 'researchnavigator-rn223'
  $env:TURSO_DATABASE_URL = Read-Host 'Turso Database URL (libsql://...)'
  $env:TURSO_AUTH_TOKEN = Read-HiddenValue 'Turso auth token (hidden)'

  $r2Keys = @()
  if ($null -ne $manifestObject.r2_object_keys) {
    $r2Keys = @($manifestObject.r2_object_keys | Where-Object { -not [string]::IsNullOrWhiteSpace([string] $_) })
  }
  if ($r2Keys.Count -gt 0) {
    $env:R2_ACCOUNT_ID = Read-Host 'R2 Account ID'
    $env:R2_ACCESS_KEY_ID = Read-Host 'R2 Access Key ID'
    $env:R2_SECRET_ACCESS_KEY = Read-HiddenValue 'R2 Secret Access Key (hidden)'
    $env:R2_BUCKET = Read-Host 'R2 Bucket'
    $env:R2_ENDPOINT = "https://$($env:R2_ACCOUNT_ID).r2.cloudflarestorage.com"
  }

  $dockerArgs = @(
    'run', '--rm',
    '--mount', "type=bind,source=$root,target=/workspace,readonly",
    '--workdir', '/workspace',
    '--env', 'DATABASE_BACKEND', '--env', 'RN223_TARGET_DATABASE',
    '--env', 'TURSO_DATABASE_URL', '--env', 'TURSO_AUTH_TOKEN'
  )
  if ($r2Keys.Count -gt 0) {
    $dockerArgs += @('--env', 'R2_ACCOUNT_ID', '--env', 'R2_ACCESS_KEY_ID', '--env', 'R2_SECRET_ACCESS_KEY', '--env', 'R2_BUCKET', '--env', 'R2_ENDPOINT')
  }
  $dockerArgs += @(
    $dockerImage,
    $pythonInImage, $controller.Replace('\', '/'), $mode,
    '--manifest', ("/workspace/" + $manifestPath.Substring($rootFull.Length).TrimStart('\','/').Replace('\','/'))
  )
  if ($ManifestSha256) { $dockerArgs += @('--manifest-sha256', $ManifestSha256) }
  & docker @dockerArgs
  exit $LASTEXITCODE
}
finally {
  foreach ($name in $envNames) {
    $value = $oldEnv[$name]
    if ($null -eq $value) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
    else { Set-Item "Env:$name" $value }
  }
}
