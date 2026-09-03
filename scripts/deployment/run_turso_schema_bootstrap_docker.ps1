param(
    [switch]$PreflightOnly,
    [switch]$LiveOnly,
    [switch]$Bootstrap,
    [switch]$VerifyBootstrap,
    [switch]$PromptHarness
)

$ErrorActionPreference = 'Stop'
$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) { $scriptPath = $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrWhiteSpace($scriptPath)) { throw 'Unable to resolve schema wrapper path.' }
$scriptDir = (Get-Item -LiteralPath $scriptPath).Directory.FullName
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir '..\..')).Path
$guard = Join-Path $projectRoot 'scripts/deployment/assert_researchnavigator_context.ps1'
& powershell -NoProfile -ExecutionPolicy Bypass -File $guard -ProjectRoot $projectRoot -Quiet
if ($LASTEXITCODE -ne 0) { throw 'Context guard failed.' }
$commit = (& git -C $projectRoot rev-parse HEAD).Trim()
if ($commit -notmatch '^[0-9a-fA-F]{40}$') { throw 'Source commit resolution failed.' }
$modeCount = @($PreflightOnly, $LiveOnly, $Bootstrap, $VerifyBootstrap).Where({ $_ }).Count
if ($modeCount -ne 1) { throw 'Choose exactly one of -PreflightOnly, -LiveOnly, -Bootstrap, or -VerifyBootstrap.' }
if ($PromptHarness -and $PreflightOnly) { throw '-PromptHarness cannot be used with -PreflightOnly.' }
$evidenceDir = Join-Path $projectRoot 'deployment/cloud/runtime_receipts'
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
$receiptPath = '/evidence/TURSO_SCHEMA_BOOTSTRAP_MIGRATION_RECEIPT.json'
$image = 'rn223-schema-audit:py312-libsql020'
if (-not (& docker image inspect $image 2>$null)) {
    throw "Verified cached image missing: $image. Build it once with deployment/cloud/parity/Dockerfile."
}
$mounts = @('--rm', '--network', 'bridge', '--mount', "type=bind,source=$projectRoot,target=/workspace,readonly", '--mount', "type=bind,source=$evidenceDir,target=/evidence", '--workdir', '/workspace', '--env', "RN_SOURCE_COMMIT=$commit", '--env', "RN_SCHEMA_RECEIPT_PATH=$receiptPath")
if ($PreflightOnly) {
    & docker run @mounts $image /opt/rn-venv/bin/python /workspace/deployment/cloud/parity/run_turso_schema_bootstrap.py --preflight
    if ($LASTEXITCODE -ne 0) { throw 'Schema preflight failed; credentials were not requested.' }
    exit 0
}
if ($Bootstrap -or $VerifyBootstrap) {
    Write-Output 'BOOTSTRAP_CONTEXT=PASS'
} else {
    Write-Output 'LIVE_ONLY_CONTEXT=PASS'
}
Write-Output "CACHED_IMAGE=$image"
if ($PromptHarness) {
    if ($Bootstrap -or $VerifyBootstrap) { Write-Output 'BOOTSTRAP_SECRET_PROMPT_REACHED=PASS' }
    else { Write-Output 'LIVE_SECRET_PROMPT_REACHED=PASS' }
    exit 0
}
$url = Read-Host 'Turso database URL (libsql://...)'
$token = Read-Host 'Turso auth token (hidden)' -AsSecureString
$env:TURSO_DATABASE_URL = $url
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($token)
try {
    $env:TURSO_AUTH_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    if ($Bootstrap) {
        & docker run @mounts --env TURSO_DATABASE_URL --env TURSO_AUTH_TOKEN $image /opt/rn-venv/bin/python /workspace/deployment/cloud/parity/run_turso_schema_bootstrap.py --bootstrap
    } elseif ($VerifyBootstrap) {
        & docker run @mounts --env TURSO_DATABASE_URL --env TURSO_AUTH_TOKEN $image /opt/rn-venv/bin/python /workspace/deployment/cloud/parity/run_turso_schema_bootstrap.py --verify-bootstrap
    } else {
        & docker run @mounts --env TURSO_DATABASE_URL --env TURSO_AUTH_TOKEN $image /opt/rn-venv/bin/python /workspace/deployment/cloud/parity/run_turso_schema_bootstrap.py --live
    }
    exit $LASTEXITCODE
} finally {
    Remove-Item Env:TURSO_DATABASE_URL,Env:TURSO_AUTH_TOKEN -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
