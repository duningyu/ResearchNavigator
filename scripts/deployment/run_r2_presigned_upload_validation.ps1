[CmdletBinding()]
param(
  [Parameter(Mandatory = $false)] [string] $ProjectRoot,
  [switch] $PreflightOnly
)

$ErrorActionPreference = 'Stop'
$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) { $scriptPath = $MyInvocation.MyCommand.Path }
$scriptDir = Split-Path -Path $scriptPath -Parent
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
  $ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir '..\..')).Path
} else {
  $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
}
$ProjectRoot = $ProjectRoot.TrimEnd('\')
if ((Split-Path -Leaf $ProjectRoot) -ne 'rn223-zero-cost-cloud-v1') {
  throw 'Resolved project root is not the expected ResearchNavigator worktree.'
}

$guard = Join-Path $ProjectRoot 'scripts/deployment/assert_researchnavigator_context.ps1'
& powershell -NoProfile -ExecutionPolicy Bypass -File $guard -ProjectRoot $ProjectRoot -Quiet
if ($LASTEXITCODE -ne 0) { throw 'Context guard failed.' }
$head = (& git -C $ProjectRoot rev-parse HEAD).Trim()
$status = @(& git -C $ProjectRoot status --porcelain)
$sourceDirty = @($status | Where-Object {
  $_ -and $_.Substring(3) -notlike 'deployment/cloud/*' -and $_.Substring(3) -notlike 'deployment/cloud\*'
})
if ($sourceDirty.Count -gt 0) { throw 'EXECUTABLE_SOURCE_DIRTY_BEFORE_LIVE_VALIDATION' }
$image = 'rn223-schema-audit:py312-libsql020'
docker image inspect $image *> $null
if ($LASTEXITCODE -ne 0) { throw "Required cached image is unavailable: $image" }
if ($PreflightOnly) {
  Write-Output 'R2_PRESIGNED_UPLOAD_PREFLIGHT=PASS'
  exit 0
}

$bucketExpected = 'researchnav-documents'
$accessPtr = [IntPtr]::Zero; $secretPtr = [IntPtr]::Zero
$account = $null; $access = $null; $secret = $null
$savedEnv = @{}
try {
  $account = Read-Host 'R2 Account ID'
  $accessSecure = Read-Host 'R2 Access Key ID (hidden)' -AsSecureString
  $secretSecure = Read-Host 'R2 Secret Access Key (hidden)' -AsSecureString
  $bucket = Read-Host "R2 bucket name [$bucketExpected]"
  if ([string]::IsNullOrWhiteSpace($bucket)) { $bucket = $bucketExpected }
  if ($bucket -ne $bucketExpected) { throw 'Bucket must be researchnav-documents.' }
  if ($account -notmatch '^[a-f0-9]{32}$') { throw 'R2 Account ID format rejected.' }
  $accessPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($accessSecure)
  $secretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secretSecure)
  $access = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($accessPtr)
  $secret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPtr)
  $endpoint = "https://$account.r2.cloudflarestorage.com"
  $runner = '/workspace/deployment/cloud/parity/run_r2_presigned_upload_validation.py'
  $receipt = '/workspace/deployment/cloud/runtime_receipts/R2_PRESIGNED_UPLOAD_SECURITY_RECEIPT.json'
  foreach ($name in @('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET', 'R2_ENDPOINT')) {
    $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
  }
  $env:R2_ACCOUNT_ID = $account
  $env:R2_ACCESS_KEY_ID = $access
  $env:R2_SECRET_ACCESS_KEY = $secret
  $env:R2_BUCKET = $bucket
  $env:R2_ENDPOINT = $endpoint
  docker run --rm --cpus=1 --memory=2g `
    -v "${ProjectRoot}:/workspace" -w /workspace `
    -e R2_ACCOUNT_ID -e R2_ACCESS_KEY_ID -e R2_SECRET_ACCESS_KEY `
    -e R2_BUCKET -e R2_ENDPOINT -e "RN_SOURCE_COMMIT=$head" `
    -e "RN_R2_RECEIPT_PATH=$receipt" $image `
    python $runner
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
  if ($accessPtr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($accessPtr) }
  if ($secretPtr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPtr) }
  $account = $null; $access = $null; $secret = $null
  foreach ($name in $savedEnv.Keys) {
    [Environment]::SetEnvironmentVariable($name, $savedEnv[$name], 'Process')
  }
}
