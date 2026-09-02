param(
  [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) { $scriptPath = $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrWhiteSpace($scriptPath)) { throw 'Unable to resolve Docker parity wrapper path.' }
$scriptDir = (Get-Item -LiteralPath $scriptPath).Directory.FullName
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir '..\..')).Path
if ((Split-Path -Leaf $projectRoot) -ne 'rn223-zero-cost-cloud-v1') { throw 'Unexpected project root.' }
$guard = Join-Path $projectRoot 'scripts/deployment/assert_researchnavigator_context.ps1'
& powershell -NoProfile -ExecutionPolicy Bypass -File $guard -ProjectRoot $projectRoot -Quiet
if ($LASTEXITCODE -ne 0) { throw 'Context guard failed.' }

$dockerImage = 'python:3.12.11-slim-bookworm'
$mount = "$projectRoot`:/workspace"
$pythonCheck = @'
import platform
import sqlalchemy
import boto3
import fastapi
import sqlalchemy_libsql
from sqlalchemy import create_engine
from research_navigator.config import normalize_turso_database_url
from research_navigator.data_plane.database import database_dialect
import run_evidence_workflow_parity
import services.worker.main
url = normalize_turso_database_url("libsql://example.turso.io")
assert database_dialect(url).name == "turso"
engine = create_engine(url)
engine.dispose()
print("LINUX_PYTHON=PASS")
print("SQLALCHEMY_LIBSQL_INSTALLED=PASS")
print("SQLALCHEMY_LIBSQL_DIALECT=PASS")
print("WORKER_IMPORT=PASS")
print("PARITY_RUNNER_IMPORT=PASS")
print("LINUX_PLATFORM=" + platform.system())
print("CLOUD_PARITY_PREFLIGHT=PASS")
'@
$pythonCheckB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pythonCheck))
$preflight = @(
  'set -eu',
  'export UV_PROJECT_ENVIRONMENT=/tmp/rn-venv',
  'export UV_CACHE_DIR=/tmp/uv-cache',
  'python -m pip install --disable-pip-version-check --no-cache-dir uv',
  'uv sync --frozen --extra dev',
  'export PYTHONPATH=/workspace/apps/api:/workspace:/workspace/deployment/cloud/parity',
  "printf %s $pythonCheckB64 | base64 -d | /tmp/rn-venv/bin/python"
) -join ' && '

if ($PreflightOnly) {
  & docker run --rm --mount "type=bind,source=$projectRoot,target=/workspace" --workdir /workspace $dockerImage sh -lc $preflight
  if ($LASTEXITCODE -ne 0) { throw 'Linux Docker parity preflight failed.' }
  exit 0
}

& docker run --rm --mount "type=bind,source=$projectRoot,target=/workspace" --workdir /workspace $dockerImage sh -lc $preflight
if ($LASTEXITCODE -ne 0) { throw 'Linux Docker parity preflight failed; credentials were not requested.' }

$env:DATABASE_BACKEND = 'turso'
$env:RN_STORAGE_BACKEND = 'r2'
$tursoUrl = Read-Host 'Turso database URL (libsql://...)'
$tursoToken = Read-Host 'Turso auth token (hidden)' -AsSecureString
$r2AccountId = Read-Host 'R2 Account ID'
$r2AccessKey = Read-Host 'R2 Access Key ID (hidden)' -AsSecureString
$r2Secret = Read-Host 'R2 Secret Access Key (hidden)' -AsSecureString
$env:TURSO_DATABASE_URL = $tursoUrl
$env:R2_ACCOUNT_ID = $r2AccountId
$env:R2_BUCKET = 'researchnav-documents'
$env:R2_ENDPOINT = "https://$r2AccountId.r2.cloudflarestorage.com"
$ptrs = @()
try {
  if ([string]::IsNullOrWhiteSpace($tursoUrl) -or [string]::IsNullOrWhiteSpace($r2AccountId)) { throw 'Required non-secret configuration is empty.' }
  foreach ($item in @(@('TURSO_AUTH_TOKEN', $tursoToken), @('R2_ACCESS_KEY_ID', $r2AccessKey), @('R2_SECRET_ACCESS_KEY', $r2Secret))) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($item[1]); $ptrs += $ptr
    Set-Item -Path "Env:$($item[0])" -Value ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr))
  }
  $runner = '/workspace/deployment/cloud/parity/run_evidence_workflow_parity.py'
  $live = $preflight + ' && /tmp/rn-venv/bin/python ' + $runner + ' prepare'
  & docker run --rm --mount "type=bind,source=$projectRoot,target=/workspace" --workdir /workspace --env DATABASE_BACKEND --env RN_STORAGE_BACKEND --env TURSO_DATABASE_URL --env TURSO_AUTH_TOKEN --env R2_ACCOUNT_ID --env R2_ACCESS_KEY_ID --env R2_SECRET_ACCESS_KEY --env R2_BUCKET --env R2_ENDPOINT $dockerImage sh -lc $live
  exit $LASTEXITCODE
}
finally {
  foreach ($name in @('DATABASE_BACKEND','RN_STORAGE_BACKEND','TURSO_DATABASE_URL','TURSO_AUTH_TOKEN','R2_ACCOUNT_ID','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY','R2_BUCKET','R2_ENDPOINT')) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
  foreach ($ptr in $ptrs) { if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) } }
}
