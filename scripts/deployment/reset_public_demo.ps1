[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [Parameter(Mandatory)] [string] $DemoDataDir,
  [string] $PythonPath,
  [string] $DemoEmail = 'demo@researchnavigator.local',
  [string] $DemoPassword = 'research-demo-223',
  [switch] $ValidateOnly
)

$ErrorActionPreference = 'Stop'
$markerKind = 'RESEARCH_NAVIGATOR_PUBLIC_DEMO_RUNTIME_V1'
$markerName = 'PUBLIC_DEMO_RUNTIME.marker'
$project = (Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd('\')
$demo = [IO.Path]::GetFullPath($DemoDataDir).TrimEnd('\')
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
) {
  throw 'DemoDataDir must not be the repository, inside the repository, or its parent.'
}

$markerPath = Join-Path $demo $markerName
if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
  throw "Public demo runtime marker is missing: $markerPath"
}
$marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
if ($marker.marker -ne $markerKind) {
  throw 'Public demo runtime marker kind is invalid.'
}
$markerProject = [IO.Path]::GetFullPath([string]$marker.project_root).TrimEnd('\')
if (-not $markerProject.Equals($project, [StringComparison]::OrdinalIgnoreCase)) {
  throw 'Public demo runtime marker belongs to another repository.'
}
if ($ValidateOnly) {
  Write-Output 'PUBLIC_DEMO_RESET_SAFETY=PASS'
  exit 0
}

if (-not $PythonPath) {
  $PythonPath = Join-Path $project '.venv/Scripts/python.exe'
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
  throw "Python environment not found: $PythonPath"
}

$statePath = Join-Path $project 'deployment/public_demo_state.json'
if (Test-Path -LiteralPath $statePath) {
  $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
  $stateDemo = [IO.Path]::GetFullPath([string]$state.demo_data_dir).TrimEnd('\')
  if (-not $stateDemo.Equals($demo, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Active public demo state belongs to a different DemoDataDir.'
  }
  & (Join-Path $project 'scripts/deployment/stop_public_demo.ps1') -ProjectRoot $project
}

$backupDir = Join-Path $demo '_reset_backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$databasePath = Join-Path $demo 'research_navigator.db'
if (Test-Path -LiteralPath $databasePath -PathType Leaf) {
  $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
  Copy-Item -LiteralPath $databasePath -Destination (Join-Path $backupDir "pre-reset-$stamp.db")
}

Get-ChildItem -LiteralPath $demo -Force |
  Where-Object { $_.Name -notin @($markerName, '_reset_backups') } |
  Remove-Item -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $demo 'logs') | Out-Null

$databaseUrlPath = $databasePath.Replace('\', '/')
$env:RN_DATA_DIR = $demo
$env:RN_DATABASE_URL = "sqlite+pysqlite:///$databaseUrlPath"
$env:RN_ENVIRONMENT = 'demo'
$env:RN_PUBLIC_DEMO_MODE = '1'
$env:RN_ENABLE_FIXTURE_SOURCE = '1'
$env:RN_ENABLE_OPENALEX = '0'
$env:RN_ENABLE_CROSSREF = '0'
$env:RN_ENABLE_ARXIV = '0'
$env:RN_ENABLE_SEMANTIC_SCHOLAR = '0'
$env:RN_ANALYSIS_PROVIDER = 'deterministic'

Push-Location $project
try {
  & $PythonPath -m alembic upgrade head
  if ($LASTEXITCODE -ne 0) { throw 'Alembic migration failed during public demo reset.' }
  & $PythonPath (Join-Path $project 'scripts/deployment/seed_public_demo.py') `
    --data-dir $demo --email $DemoEmail --password $DemoPassword
  if ($LASTEXITCODE -ne 0) { throw 'Public demo seed failed.' }
} finally {
  Pop-Location
}

$receipt = Get-Content -LiteralPath (Join-Path $demo 'seed_receipt.json') -Raw | ConvertFrom-Json
if ($receipt.integrity_check -ne 'ok' -or -not $receipt.fixture_only) {
  throw 'Public demo reset verification failed.'
}
Write-Output 'PUBLIC_DEMO_RESET=PASS'
