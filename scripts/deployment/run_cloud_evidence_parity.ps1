param(
  [switch]$PreflightOnly,
  [switch]$ConfigPreflight
)
$ErrorActionPreference = 'Stop'
$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) { $scriptPath = $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrWhiteSpace($scriptPath)) { throw 'Unable to resolve parity wrapper path.' }
$scriptDir = (Get-Item -LiteralPath $scriptPath).Directory.FullName
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir '..\..')).Path
if ((Split-Path -Leaf $projectRoot) -ne 'rn223-zero-cost-cloud-v1') { throw 'Unexpected project root.' }
$guard = Join-Path $projectRoot 'scripts/deployment/assert_researchnavigator_context.ps1'
& powershell -NoProfile -ExecutionPolicy Bypass -File $guard -ProjectRoot $projectRoot -Quiet
if ($LASTEXITCODE -ne 0) { throw 'Context guard failed.' }
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Project .venv Python is unavailable.' }
if ($PreflightOnly) {
  & $python -c "import boto3, botocore, sqlalchemy, research_navigator, reportlab"
  if ($LASTEXITCODE -ne 0) { throw 'Parity runtime dependencies are unavailable.' }
  $runner = Join-Path $projectRoot 'deployment/cloud/parity/run_evidence_workflow_parity.py'
  $receiptDir = Join-Path $projectRoot 'deployment/cloud'
  if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'Parity runner is unavailable.' }
  if (-not (Test-Path -LiteralPath $receiptDir -PathType Container)) { throw 'Receipt directory is unavailable.' }
  Write-Output 'CLOUD_PARITY_PREFLIGHT=PASS'
  exit 0
}
$env:DATABASE_BACKEND='turso'; $env:RN_STORAGE_BACKEND='r2'
$tursoUrl = Read-Host 'Turso database URL'
$tursoToken = Read-Host 'Turso auth token (hidden)' -AsSecureString
$r2AccountId = Read-Host 'R2 Account ID'
$r2AccessKey = Read-Host 'R2 Access Key ID (hidden)' -AsSecureString
$r2Secret = Read-Host 'R2 Secret Access Key (hidden)' -AsSecureString
$r2Bucket = 'researchnav-documents'
$r2Endpoint = "https://$r2AccountId.r2.cloudflarestorage.com"
$env:TURSO_DATABASE_URL = $tursoUrl
$env:R2_ACCOUNT_ID = $r2AccountId
$env:R2_BUCKET = $r2Bucket
$env:R2_ENDPOINT = $r2Endpoint
$ptrs = @()
try {
  if ([string]::IsNullOrWhiteSpace($tursoUrl) -or [string]::IsNullOrWhiteSpace($r2AccountId)) { throw 'Required non-secret configuration is empty.' }
  foreach ($item in @(@('TURSO_AUTH_TOKEN',$tursoToken), @('R2_ACCESS_KEY_ID',$r2AccessKey), @('R2_SECRET_ACCESS_KEY',$r2Secret))) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($item[1]); $ptrs += $ptr
    Set-Item -Path "Env:$($item[0])" -Value ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr))
  }
  $runner = Join-Path $projectRoot 'deployment/cloud/parity/run_evidence_workflow_parity.py'
  if ($ConfigPreflight) {
    & $python $runner config
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    exit 0
  }
  $prepareJson = (& $python $runner prepare | Out-String).Trim()
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  $state = $prepareJson | ConvertFrom-Json
  & $python (Join-Path $projectRoot 'deployment/cloud/parity/run_evidence_workflow_parity.py') reload --execution-id $state.execution_id --job-id $state.job_id --document-id $state.document_id --fixture-sha256 $state.fixture_sha256
  exit $LASTEXITCODE
} finally {
  foreach ($name in @('DATABASE_BACKEND','TURSO_DATABASE_URL','TURSO_AUTH_TOKEN','R2_ACCOUNT_ID','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY','R2_BUCKET','R2_ENDPOINT','RN_STORAGE_BACKEND')) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
  foreach ($ptr in $ptrs) { if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) } }
}
