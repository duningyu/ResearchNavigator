param([switch]$PreflightOnly)

$ErrorActionPreference = "Stop"
$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) { $scriptPath = $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrWhiteSpace($scriptPath)) { throw "Unable to resolve offline parity script path" }
$scriptDir = Split-Path -Path $scriptPath -Parent
$projectRoot = ((Resolve-Path -LiteralPath (Join-Path $scriptDir "..\..\")).Path).TrimEnd('\', '/')
Push-Location $projectRoot
try {
    $root = (Resolve-Path -Path (git rev-parse --show-toplevel).Trim()).Path
    $branch = (git branch --show-current).Trim()
    $commit = (git rev-parse HEAD).Trim()
    if ($root -ne $projectRoot -or $branch -ne "deployment/rn223-zero-cost-cloud-v1" -or $commit -notmatch '^[0-9a-f]{40}$') {
        throw "Offline parity context guard failed"
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts\deployment\assert_researchnavigator_context.ps1") -ProjectRoot $projectRoot
    if ($LASTEXITCODE -ne 0) { throw "Context guard failed" }

    $tag = "researchnavigator-parity:$($commit.Substring(0,12))"
    $imagePresent = $true
    try { docker image inspect $tag *> $null } catch { $imagePresent = $false }
    if (-not $imagePresent) {
        docker build --file (Join-Path $projectRoot "deployment\cloud\parity\Dockerfile") --tag $tag $projectRoot
        if ($LASTEXITCODE -ne 0) { throw "Parity image build failed" }
    }
    docker run --rm --network none --mount "type=bind,source=$projectRoot,target=/workspace,readonly" --workdir /workspace --env "RN_SOURCE_COMMIT=$commit" --env RN_SOURCE_COMMIT_SOURCE=HOST_CONTEXT_GUARD $tag python -c "import sqlalchemy_libsql; from sqlalchemy import create_engine; from services.worker.main import run_once; from deployment.cloud.parity import run_offline_parity; e=create_engine('sqlite+libsql://offline.invalid?secure=true'); assert e.dialect.driver == 'libsql'; print('LINUX_PARITY_PREFLIGHT=PASS')"
    if ($LASTEXITCODE -ne 0) { throw "Offline image preflight failed" }

    if ($PreflightOnly) {
        $receipts = 1..2 | ForEach-Object { Join-Path $projectRoot "deployment\cloud\OFFLINE_PARITY_HARNESS_RECEIPT_RUN_$_.json" }
        $canonical = Join-Path $projectRoot "deployment\cloud\OFFLINE_PARITY_HARNESS_RECEIPT.json"
        if (($receipts | Where-Object { -not (Test-Path -LiteralPath $_) }).Count -gt 0 -or -not (Test-Path -LiteralPath $canonical)) { throw "Offline E2E receipts are incomplete" }
        Write-Output "OFFLINE_E2E_LAST_3_RUNS=PASS"
        Write-Output "OFFLINE_NO_SECRET_PREFLIGHT=PASS"
        exit 0
    }

    1..3 | ForEach-Object {
        $run = $_
        $provider = Join-Path $env:TEMP "rn223-offline-provider-$([guid]::NewGuid().ToString('N'))"
        New-Item -ItemType Directory -Path $provider | Out-Null
        try {
            $containerProvider = "/tmp/provider-$run"
            docker run --rm --network none --mount "type=bind,source=$projectRoot,target=/workspace" --mount "type=bind,source=$provider,target=$containerProvider" --workdir /workspace --env "RN_SOURCE_COMMIT=$commit" --env RN_SOURCE_COMMIT_SOURCE=HOST_CONTEXT_GUARD $tag python /workspace/deployment/cloud/parity/run_offline_parity.py prepare --provider-root $containerProvider --workspace "/tmp/app-$run"
            if ($LASTEXITCODE -ne 0) { throw "Offline prepare run $run failed" }
            $receiptPath = Join-Path $projectRoot "deployment\cloud\OFFLINE_PARITY_HARNESS_RECEIPT_RUN_$run.json"
            if ($run -eq 3) { $receiptPath = Join-Path $projectRoot "deployment\cloud\OFFLINE_PARITY_HARNESS_RECEIPT.json" }
            $containerReceipt = "/workspace/deployment/cloud/$(Split-Path -Leaf $receiptPath)"
            docker run --rm --network none --mount "type=bind,source=$projectRoot,target=/workspace" --mount "type=bind,source=$provider,target=$containerProvider" --workdir /workspace --env "RN_SOURCE_COMMIT=$commit" --env RN_SOURCE_COMMIT_SOURCE=HOST_CONTEXT_GUARD $tag python /workspace/deployment/cloud/parity/run_offline_parity.py reload --provider-root $containerProvider --receipt $containerReceipt
            if ($LASTEXITCODE -ne 0) { throw "Offline reload run $run failed" }
        } finally {
            if (Test-Path -LiteralPath $provider) { Remove-Item -LiteralPath $provider -Recurse -Force }
        }
    }
    Write-Output "OFFLINE_E2E_LAST_3_RUNS=PASS"
} finally { Pop-Location }
