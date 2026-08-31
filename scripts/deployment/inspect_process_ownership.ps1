[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $SnapshotPath,
  [Parameter(Mandatory)] [int] $RootPid,
  [Parameter(Mandatory)] [string] $RootCreationTimeUtc,
  [Parameter(Mandatory)] [string] $SnapshotTimeUtc,
  [string] $OutputPath
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'PublicDemoProcessOwnership.psm1') -Force
$snapshot = @(Get-Content -LiteralPath $SnapshotPath -Raw | ConvertFrom-Json)
$result = Resolve-PublicDemoOwnedProcessTree `
  -Snapshot $snapshot `
  -RootPid $RootPid `
  -RootCreationTimeUtc $RootCreationTimeUtc `
  -SnapshotTimeUtc $SnapshotTimeUtc
$json = $result | ConvertTo-Json -Depth 8
if ($OutputPath) {
  $json | Set-Content -LiteralPath $OutputPath -Encoding utf8
}
Write-Output $json
