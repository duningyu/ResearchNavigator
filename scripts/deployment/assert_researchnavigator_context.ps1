[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [switch] $Quiet
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path.TrimEnd('\')

function Refuse([string] $Code, [string] $Message) {
  [Console]::Error.WriteLine("${Code}: $Message")
  exit 1
}

if ($root -match '(?i)insightforge') {
  Refuse 'INSIGHTFORGE_ROOT_REFUSED' "Project root is not ResearchNavigator: $root"
}

$gitRoot = (& git -C $root rev-parse --show-toplevel 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or -not $gitRoot) { Refuse 'GIT_ROOT_INVALID' 'ProjectRoot is not inside a Git worktree.' }
$gitRoot = (Resolve-Path -LiteralPath $gitRoot).Path.TrimEnd('\')
if (-not $gitRoot.Equals($root, [StringComparison]::OrdinalIgnoreCase)) {
  Refuse 'GIT_ROOT_MISMATCH' "Resolved Git root differs from ProjectRoot: $gitRoot"
}

$head = (& git -C $root rev-parse HEAD 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or -not $head) { Refuse 'HEAD_INVALID' 'Unable to resolve current Git HEAD.' }
$frozen = '0db09b07b3b9aa8efa8ff080c296f15bf08f5e97'
& git -C $root merge-base --is-ancestor $frozen HEAD 2>$null
if ($LASTEXITCODE -ne 0) { Refuse 'LINEAGE_MISMATCH' "Frozen core $frozen is not an ancestor of $head." }

$versionText = Get-Content -LiteralPath (Join-Path $root 'pyproject.toml') -Raw -ErrorAction SilentlyContinue
if ($versionText -notmatch '(?m)^version\s*=\s*["'']2\.2\.3["'']') {
  Refuse 'VERSION_MISMATCH' 'pyproject.toml does not declare version 2.2.3.'
}

$fingerprints = @(
  [pscustomobject]@{ name='RN_API_MODULE'; path='apps/api/research_navigator/__init__.py' },
  [pscustomobject]@{ name='PUBLIC_DEMO_START'; path='scripts/deployment/start_public_demo.ps1' },
  [pscustomobject]@{ name='PUBLIC_DEMO_RECEIPT'; path='deployment/PUBLIC_DEMO_DEPLOYMENT_RECEIPT.json' },
  [pscustomobject]@{ name='OWNERSHIP_MODULE'; path='scripts/deployment/PublicDemoProcessOwnership.psm1' },
  [pscustomobject]@{ name='OWNERSHIP_TEST'; path='tests/deployment/test_public_demo_process_ownership.py' },
  [pscustomobject]@{ name='RN_WEB_PACKAGE'; path='apps/web/package.json' }
)
$present = @($fingerprints | Where-Object { Test-Path -LiteralPath (Join-Path $root $_.path) -PathType Leaf })
if ($present.Count -lt 4) {
  $names = ($present | ForEach-Object { $_.name }) -join ', '
  Refuse 'FINGERPRINT_MISSING' "Only $($present.Count)/$($fingerprints.Count) product fingerprints present: $names"
}

$deploymentScripts = @('start_public_demo.ps1','stop_public_demo.ps1','status_public_demo.ps1','reset_public_demo.ps1')
foreach ($script in $deploymentScripts) {
  if (-not (Test-Path -LiteralPath (Join-Path $root "scripts/deployment/$script") -PathType Leaf)) {
    Refuse 'DEPLOYMENT_FILES_MISSING' "Required deployment script missing: $script"
  }
}

if (-not $Quiet) {
  [ordered]@{
    status = 'PASS'
    project = 'ResearchNavigator'
    version = '2.2.3'
    repo_root = $root
    head = $head
    frozen_core = $frozen
    fingerprints = $present.Count
  } | ConvertTo-Json -Compress
  Write-Output 'RESEARCHNAVIGATOR_CONTEXT=PASS'
}
