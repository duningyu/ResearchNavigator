param(
  [switch]$PreflightOnly,
  [switch]$RecoverThenRun,
  [string]$RecoverExecutionId,
  [int]$RecoverJobId,
  [int]$RecoverDocumentId,
  [int]$RecoverUserId,
  [string]$RecoverFixtureSha256
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
$hostRoot = (& git -C $projectRoot rev-parse --show-toplevel).Trim()
$hostBranch = (& git -C $projectRoot branch --show-current).Trim()
$hostCommit = (& git -C $projectRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($hostCommit)) { throw 'Host git source resolution failed.' }
if ((Resolve-Path -LiteralPath $hostRoot).Path -ne (Resolve-Path -LiteralPath $projectRoot).Path -or $hostBranch -ne 'deployment/rn223-zero-cost-cloud-v1') { throw 'Host git context mismatch.' }
if ($hostCommit -notmatch '^[0-9a-fA-F]{40}$') { throw 'Host git commit format invalid.' }

$dockerImage = 'rn223-schema-audit:py312-libsql020'
$pythonInImage = '/opt/rn-venv/bin/python'
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
import os
assert len(os.environ.get("RN_SOURCE_COMMIT", "")) == 40
assert os.environ.get("RN_SOURCE_COMMIT_SOURCE") == "HOST_CONTEXT_GUARD"
assert run_evidence_workflow_parity.resolve_source_commit() == os.environ["RN_SOURCE_COMMIT"]
url = normalize_turso_database_url("libsql://example.turso.io")
assert database_dialect(url).name == "turso"
engine = create_engine(url)
engine.dispose()
print("LINUX_PYTHON=PASS")
print("SQLALCHEMY_LIBSQL_INSTALLED=PASS")
print("SQLALCHEMY_LIBSQL_DIALECT=PASS")
print("WORKER_IMPORT=PASS")
print("PARITY_RUNNER_IMPORT=PASS")
print("SOURCE_COMMIT_INPUT=PASS")
print("SOURCE_COMMIT_RESOLUTION=PASS")
print("CONTAINER_GIT=NOT_REQUIRED_FOR_PARITY_RUNTIME")
print("LINUX_PLATFORM=" + platform.system())
print("CLOUD_PARITY_PREFLIGHT=PASS")
'@
$pythonCheckB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pythonCheck))
$env:RN_SOURCE_COMMIT = $hostCommit
$env:RN_SOURCE_COMMIT_SOURCE = 'HOST_CONTEXT_GUARD'
$preflight = @(
  'set -eu',
  'export PYTHONPATH=/workspace/apps/api:/workspace:/workspace/deployment/cloud/parity',
  "printf %s $pythonCheckB64 | base64 -d | $pythonInImage"
) -join ' && '

if ($PreflightOnly) {
  & docker run --rm --mount "type=bind,source=$projectRoot,target=/workspace" --workdir /workspace --env RN_SOURCE_COMMIT --env RN_SOURCE_COMMIT_SOURCE $dockerImage sh -lc $preflight
  if ($LASTEXITCODE -ne 0) { throw 'Linux Docker parity preflight failed.' }
  exit 0
}

if ($RecoverThenRun -and (
  [string]::IsNullOrWhiteSpace($RecoverExecutionId) -or
  $RecoverJobId -le 0 -or
  $RecoverDocumentId -le 0 -or
  $RecoverUserId -le 0 -or
  [string]::IsNullOrWhiteSpace($RecoverFixtureSha256)
)) { throw 'RecoverThenRun requires complete fixture identity arguments.' }

& docker run --rm --mount "type=bind,source=$projectRoot,target=/workspace" --workdir /workspace --env RN_SOURCE_COMMIT --env RN_SOURCE_COMMIT_SOURCE $dockerImage sh -lc $preflight
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
  $dockerArgs = @(
    'run', '--rm', '--mount', "type=bind,source=$projectRoot,target=/workspace",
    '--workdir', '/workspace', '--env', 'DATABASE_BACKEND', '--env', 'RN_STORAGE_BACKEND',
    '--env', 'RN_SOURCE_COMMIT', '--env', 'RN_SOURCE_COMMIT_SOURCE', '--env', 'TURSO_DATABASE_URL',
    '--env', 'TURSO_AUTH_TOKEN', '--env', 'R2_ACCOUNT_ID', '--env', 'R2_ACCESS_KEY_ID',
    '--env', 'R2_SECRET_ACCESS_KEY', '--env', 'R2_BUCKET', '--env', 'R2_ENDPOINT', $dockerImage,
    $pythonInImage, $runner
  )
  if ($RecoverThenRun) {
    & docker @dockerArgs 'recover' '--execution-id' $RecoverExecutionId '--job-id' $RecoverJobId '--document-id' $RecoverDocumentId '--user-id' $RecoverUserId '--fixture-sha256' $RecoverFixtureSha256
    if ($LASTEXITCODE -ne 0) { throw 'Orphan fixture recovery failed; authoritative parity was not started.' }
  }
  $prepareOutput = [IO.Path]::GetTempFileName()
  try {
    & docker @dockerArgs 'prepare' 1> $prepareOutput
    if ($LASTEXITCODE -ne 0) { throw 'Parity process A failed; process B was not started.' }
    $prepareJson = (Get-Content -LiteralPath $prepareOutput -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($prepareJson)) { throw 'Parity process A returned no JSON.' }
    try { $state = $prepareJson | ConvertFrom-Json } catch { throw 'Parity process A returned invalid JSON.' }
    foreach ($name in @('execution_id','job_id','document_id','user_id','paper_id','stored_key','fixture_sha256')) {
      if ($null -eq $state.$name) { throw "Parity prepare JSON missing $name." }
    }
  } finally {
    Remove-Item -LiteralPath $prepareOutput -Force -ErrorAction SilentlyContinue
  }
  & docker @dockerArgs 'reload' '--execution-id' $state.execution_id '--job-id' $state.job_id '--document-id' $state.document_id '--user-id' $state.user_id '--fixture-sha256' $state.fixture_sha256
  if ($LASTEXITCODE -ne 0) { throw 'Parity process B failed; final PASS was not established.' }
  $receiptPath = Join-Path $projectRoot 'deployment/cloud/runtime_receipts/RN223_R2_TURSO_EVIDENCE_WORKFLOW_LIVE_PARITY_RECEIPT.json'
  if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) { throw 'Final parity receipt is missing.' }
  $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
  if ($receipt.final_status -ne 'PASS') { throw 'Final parity receipt did not report PASS.' }
  exit 0
}
finally {
  foreach ($name in @('DATABASE_BACKEND','RN_STORAGE_BACKEND','RN_SOURCE_COMMIT','RN_SOURCE_COMMIT_SOURCE','TURSO_DATABASE_URL','TURSO_AUTH_TOKEN','R2_ACCOUNT_ID','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY','R2_BUCKET','R2_ENDPOINT')) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
  foreach ($ptr in $ptrs) { if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) } }
}
