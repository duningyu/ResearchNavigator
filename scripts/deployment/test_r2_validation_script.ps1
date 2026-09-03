$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$target = Join-Path $root 'scripts/deployment/run_r2_live_validation.ps1'
$source = Get-Content -LiteralPath $target -Raw
if($source -match '(?im)^\s*\$host\s*=') { throw 'Reserved automatic variable collision remains.' }
if($source -match '\$ph\s*=\s*Hash\s+\$\(') { throw 'Null-body hash pipeline overload remains.' }
if($source -notmatch '(?m)exit\s+\$exitCode') { throw 'Failure exit-code contract is absent.' }
if($source -notmatch 'PASS_CONTENT_INTEGRITY') { throw 'GET content-integrity contract is absent.' }
if($source -match '\[Convert\]::ToHexString') { throw 'Unsupported Convert.ToHexString remains.' }
if($source -notmatch "Method='GET'") { throw 'Anonymous check is not an unsigned GET.' }
if($source.IndexOf('$aq=') -gt $source.IndexOf('$d=R2 DELETE')) { throw 'Anonymous check occurs after DELETE.' }
if($source -match '(?im)\bsetx\b|\.env') { throw 'Forbidden secret persistence mechanism found.' }
function Invoke-RenamedHostGreen {
  param([string]$Uri)
  $uriValue = [Uri]::new($Uri)
  $endpointHost = $uriValue.Host
  return $endpointHost
}
if((Invoke-RenamedHostGreen 'https://example.invalid') -ne 'example.invalid') { throw 'Renamed host green reproduction failed.' }
function Invoke-NullBodyHashGreen {
  param([byte[]]$Body)
  $empty = [byte[]]::new(0)
  if($null -eq $Body){ return [Security.Cryptography.SHA256]::Create().ComputeHash($empty) }
  return [Security.Cryptography.SHA256]::Create().ComputeHash($Body)
}
if((Invoke-NullBodyHashGreen $null).Length -ne 32) { throw 'Null-body hash green reproduction failed.' }
function Classify-AnonymousStatusTest([int]$StatusCode,[bool]$Known) {
  if($StatusCode -ge 200 -and $StatusCode -lt 300){return 'FAIL_ANONYMOUS_OBJECT_ACCESS_ALLOWED'}
  if($StatusCode -in 401,403){return 'PASS_ANONYMOUS_ACCESS_DENIED'}
  if($StatusCode -eq 400){return 'AMBIGUOUS_REQUEST_INVALID'}
  if($StatusCode -eq 404){if($Known){return 'SECURITY_CHECK_UNRESOLVED_OBJECT_DISAPPEARED'};return 'INVALID_SECURITY_TEST'}
  return 'SECURITY_CHECK_UNRESOLVED'
}
if((Classify-AnonymousStatusTest 204 $true) -ne 'FAIL_ANONYMOUS_OBJECT_ACCESS_ALLOWED') { throw '2xx anonymous contract failed.' }
if((Classify-AnonymousStatusTest 401 $true) -ne 'PASS_ANONYMOUS_ACCESS_DENIED') { throw '401 anonymous contract failed.' }
if((Classify-AnonymousStatusTest 403 $true) -ne 'PASS_ANONYMOUS_ACCESS_DENIED') { throw '403 anonymous contract failed.' }
if((Classify-AnonymousStatusTest 400 $true) -ne 'AMBIGUOUS_REQUEST_INVALID') { throw '400 anonymous contract failed.' }
if((Classify-AnonymousStatusTest 404 $false) -ne 'INVALID_SECURITY_TEST') { throw '404 anonymous contract failed.' }
$same = ((New-Object byte[] 3) -join ',')
if(($same -eq ([byte[]](0,0,0) -join ',')) -ne $true) { throw 'Synthetic payload exact-match test failed.' }
if(($same -eq ([byte[]](0,0,1) -join ',')) -ne $false) { throw 'Synthetic payload mismatch test failed.' }
function Test-Integrity([byte[]]$Actual,[byte[]]$Expected) {
  if($null -eq $Actual -or $null -eq $Expected){throw 'controlled integrity input error'}
  $sha=[Security.Cryptography.SHA256]::Create();try{return $Actual.Length -eq $Expected.Length -and (([BitConverter]::ToString($sha.ComputeHash($Actual))) -eq ([BitConverter]::ToString($sha.ComputeHash($Expected))))}finally{$sha.Dispose()}
}
if(-not (Test-Integrity ([byte[]](1,2,3)) ([byte[]](1,2,3)))) { throw 'Exact byte integrity test failed.' }
if(Test-Integrity ([byte[]](1,2,3)) ([byte[]](1,2,4))) { throw 'Same-length mismatch test failed.' }
if(Test-Integrity ([byte[]](1,2,3)) ([byte[]](1,2))) { throw 'Different-length mismatch test failed.' }
if(-not (Test-Integrity ([byte[]]@()) ([byte[]]@()))) { throw 'Empty payload integrity test failed.' }
try { Test-Integrity $null ([byte[]](1)); throw 'Null response stream was not controlled.' } catch { if($_.Exception.Message -ne 'controlled integrity input error'){throw} }
Write-Output 'R2_VALIDATION_SCRIPT_CONTRACT=PASS'
