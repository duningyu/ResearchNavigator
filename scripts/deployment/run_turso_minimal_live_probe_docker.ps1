param([switch]$PreflightOnly)

$ErrorActionPreference = 'Stop'
$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) { $scriptPath = $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrWhiteSpace($scriptPath)) { throw 'Unable to resolve probe wrapper path.' }
$scriptDir = (Get-Item -LiteralPath $scriptPath).Directory.FullName
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir '..\..')).Path
$guard = Join-Path $projectRoot 'scripts/deployment/assert_researchnavigator_context.ps1'
& powershell -NoProfile -ExecutionPolicy Bypass -File $guard -ProjectRoot $projectRoot -Quiet
if ($LASTEXITCODE -ne 0) { throw 'Context guard failed.' }
$commit = (& git -C $projectRoot rev-parse HEAD).Trim()
if ($commit -notmatch '^[0-9a-fA-F]{40}$') { throw 'Source commit resolution failed.' }
$image = 'python:3.12.11-slim-bookworm'
$mount = "${projectRoot}:/workspace"
$preflight = 'set -eu; export UV_PROJECT_ENVIRONMENT=/tmp/rn-venv; export UV_CACHE_DIR=/tmp/uv-cache; python -m pip install --disable-pip-version-check --no-cache-dir uv >/dev/null; uv sync --frozen --extra dev >/dev/null; export PYTHONPATH=/workspace/apps/api:/workspace; /tmp/rn-venv/bin/python /workspace/deployment/cloud/parity/probe_turso_minimal.py --preflight'
& docker run --rm --mount "type=bind,source=$projectRoot,target=/workspace,readonly" --workdir /workspace --env RN_SOURCE_COMMIT=$commit $image sh -lc $preflight
if ($LASTEXITCODE -ne 0) { throw 'Probe preflight failed; credentials were not requested.' }
if ($PreflightOnly) { exit 0 }
$url = Read-Host 'Turso database URL (libsql://...)'
$token = Read-Host 'Turso auth token (hidden)' -AsSecureString
$env:TURSO_DATABASE_URL = $url
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($token)
try {
    $env:TURSO_AUTH_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    & docker run --rm --network bridge --mount "type=bind,source=$projectRoot,target=/workspace,readonly" --workdir /workspace --env TURSO_DATABASE_URL --env TURSO_AUTH_TOKEN $image sh -lc ($preflight + '; /tmp/rn-venv/bin/python /workspace/deployment/cloud/parity/probe_turso_minimal.py --live')
    exit $LASTEXITCODE
} finally {
    Remove-Item Env:TURSO_DATABASE_URL,Env:TURSO_AUTH_TOKEN -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
