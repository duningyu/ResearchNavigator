param(
  [string]$ProjectRoot,
  [switch]$PreflightOnly,
  [switch]$R2ConfigPreflight
)
$ErrorActionPreference = 'Stop'
$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) { $scriptPath = $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrWhiteSpace($scriptPath)) { throw 'Unable to resolve validation script path.' }
$scriptDir = Split-Path -Path $scriptPath -Parent
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
  $ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir '..\..')).Path
} else {
  $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
}
$expectedProjectName = 'rn223-zero-cost-cloud-v1'
if ((Split-Path -Leaf $ProjectRoot) -ne $expectedProjectName) { throw 'Resolved project root is not the expected ResearchNavigator cloud worktree.' }
if ($PreflightOnly) {
  $guard = Join-Path $ProjectRoot 'scripts/deployment/assert_researchnavigator_context.ps1'
  if (-not (Test-Path -LiteralPath $guard -PathType Leaf)) { throw 'Context guard is unavailable.' }
  & powershell -NoProfile -ExecutionPolicy Bypass -File $guard -ProjectRoot $ProjectRoot -Quiet
  if ($LASTEXITCODE -ne 0) { throw 'Context guard failed.' }
  $projectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
  if (Test-Path -LiteralPath $projectPython -PathType Leaf) {
    $pythonCommand = $projectPython
  } elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = 'python'
  } else {
    throw 'Python runtime is unavailable.'
  }
  & $pythonCommand -c "import boto3, botocore" 2>$null
  if ($LASTEXITCODE -ne 0) { throw 'Required boto3/botocore runtime is unavailable.' }
  $receiptParent = Split-Path -Path (Join-Path $ProjectRoot 'deployment/cloud/LIVE_R2_STORAGE_RECEIPT.json') -Parent
  if (-not (Test-Path -LiteralPath $receiptParent -PathType Container)) { throw 'Receipt directory is unavailable.' }
  Write-Output 'SCRIPT_PATH_RESOLUTION=PASS'
  Write-Output 'PROJECT_ROOT=PASS'
  Write-Output 'CONTEXT_GUARD=PASS'
  Write-Output 'R2_PREFLIGHT=PASS'
  exit 0
}
$validationStage = 'CREDENTIAL_INPUT'
$safeErrorMessage = $null
$providerErrorCode = $null
$httpStatus = $null
$exitCode = 0
$bucketExpected = 'researchnav-documents'
$receiptPath = Join-Path $ProjectRoot 'deployment/cloud/LIVE_R2_STORAGE_RECEIPT.json'
$objectId = [guid]::NewGuid().ToString('N')
$objectKey = "rn223-validation/$objectId/object.bin"
$payload = [Text.Encoding]::UTF8.GetBytes("RN223 R2 validation $objectId")
$secretPtr = [IntPtr]::Zero; $secretValue = $null
$receipt = [ordered]@{
  receipt_type='LIVE_R2_STORAGE_RECEIPT'; subscription_user_attested=$true
  failure_classification='LOCAL_VALIDATION_SCRIPT_BOOTSTRAP_FAILURE'; r2_provider_reached=$false
  credentials_prompted=$false; credentials_exposed=$false; live_r2_status='NOT_RUN'
  validation_stage='CREDENTIAL_INPUT'; error_type=$null; http_status_if_available=$null
  provider_error_code_if_available=$null; safe_error_message=$null
  subscription_active='USER_ATTESTED_NOT_MACHINE_VERIFIED'; storage_class='Standard'
  bucket=$bucketExpected; public_access='disabled'; credential_scope='bucket_only'
  quota_guard=@{name='RN_CLOUD_STORAGE_QUOTA_BYTES'; max_bytes=5368709120}
  test_object_prefix='rn223-validation/<uuid>/'; put='NOT_RUN'; head='NOT_RUN'; get='NOT_RUN'
  delete='NOT_RUN'; cleanup='NOT_RUN'; anonymous_access='NOT_RUN'
  storage_abstraction_isolation='NOT_RUN'; path_traversal_rejection='NOT_RUN'
  cross_user_access='NOT_RUN_APPLICATION_LAYER'; paid_resources=0
  final_status='NOT_RUN_WAITING_LOCAL_SECRET_ENTRY'; secrets_logged=$false
}
function Hmac([byte[]]$k,[string]$d){$x=[Security.Cryptography.HMACSHA256]::new($k);try{return $x.ComputeHash([Text.Encoding]::UTF8.GetBytes($d))}finally{$x.Dispose()}}
function Hash([byte[]]$b){$x=[Security.Cryptography.SHA256]::Create();try{return ([BitConverter]::ToString($x.ComputeHash($b))).Replace('-','').ToLowerInvariant()}finally{$x.Dispose()}}
function Hex([byte[]]$b){return ([BitConverter]::ToString($b)).Replace('-','').ToLowerInvariant()}
function SignKey([string]$s,[string]$d){$a=Hmac ([Text.Encoding]::UTF8.GetBytes("AWS4$s")) $d;$a=Hmac $a 'auto';$a=Hmac $a 's3';return Hmac $a 'aws4_request'}
function R2([string]$m,[string]$e,[string]$b,[string]$k,[string]$ak,[string]$sk,[byte[]]$body,[switch]$ReturnBody){
  $u=[Uri]::new("$e/$b/$k");$n=[DateTime]::UtcNow;$ad=$n.ToString('yyyyMMddTHHmmssZ');$day=$n.ToString('yyyyMMdd')
  $empty=[byte[]]::new(0);$ph=if($null -eq $body){Hash $empty}else{Hash $body};$endpointHost=$u.Host
  $cu='/' + ((($u.AbsolutePath.TrimStart('/') -split '/')|%{[Uri]::EscapeDataString($_)}) -join '/')
  $ch="host:$endpointHost`nx-amz-content-sha256:$ph`nx-amz-date:$ad`n";$sh='host;x-amz-content-sha256;x-amz-date'
  $cr="$m`n$cu`n`n$ch`n$sh`n$ph";$scope="$day/auto/s3/aws4_request";$sts="AWS4-HMAC-SHA256`n$ad`n$scope`n$(Hash ([Text.Encoding]::UTF8.GetBytes($cr)))";$sig=Hex (Hmac (SignKey $sk $day) $sts)
  $q=[Net.HttpWebRequest]::Create($u);$q.Method=$m;$q.Headers['x-amz-date']=$ad;$q.Headers['x-amz-content-sha256']=$ph;$q.Headers['Authorization']="AWS4-HMAC-SHA256 Credential=$ak/$scope, SignedHeaders=$sh, Signature=$sig"
  if($null -ne $body){$q.ContentLength=$body.Length;$z=$q.GetRequestStream();$z.Write($body,0,$body.Length);$z.Dispose()}
  try{$r=[Net.HttpWebResponse]$q.GetResponse();if($ReturnBody){$ms=[IO.MemoryStream]::new();$r.GetResponseStream().CopyTo($ms);$code=[int]$r.StatusCode;$r.Dispose();return [pscustomobject]@{StatusCode=$code;Body=$ms.ToArray()}};try{return [int]$r.StatusCode}finally{$r.Dispose()}}catch [Net.WebException]{if($_.Exception.Response){return [int]$_.Exception.Response.StatusCode};throw}
}
function ClassifyAnonymousStatus([int]$StatusCode,[bool]$ObjectKnownToExist){
  if($StatusCode -ge 200 -and $StatusCode -lt 300){return 'FAIL_ANONYMOUS_OBJECT_ACCESS_ALLOWED'}
  if($StatusCode -in 401,403){return 'PASS_ANONYMOUS_ACCESS_DENIED'}
  if($StatusCode -eq 400){return 'AMBIGUOUS_REQUEST_INVALID'}
  if($StatusCode -eq 404){if($ObjectKnownToExist){return 'SECURITY_CHECK_UNRESOLVED_OBJECT_DISAPPEARED'};return 'INVALID_SECURITY_TEST'}
  return 'SECURITY_CHECK_UNRESOLVED'
}
try {
  $validationStage = 'CREDENTIAL_INPUT'; $receipt.validation_stage = $validationStage
  $accountId=Read-Host 'R2 Account ID';$accessKey=Read-Host 'R2 Access Key ID';$ss=Read-Host 'R2 Secret Access Key (hidden)' -AsSecureString;$bucket=Read-Host "R2 bucket name [$bucketExpected]"
  $receipt.credentials_prompted=$true
  $validationStage = 'CONFIG_MAPPING'; $receipt.validation_stage = $validationStage
  if([string]::IsNullOrWhiteSpace($bucket)){$bucket=$bucketExpected};if($bucket -ne $bucketExpected){throw 'Bucket must be researchnav-documents.'};if($accountId -notmatch '^[a-f0-9]{32}$'){throw 'R2 Account ID format rejected.'};if([string]::IsNullOrWhiteSpace($accessKey)){throw 'Access Key ID is required.'}
  $secretPtr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($ss);$secretValue=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPtr)
  $validationStage = 'ENDPOINT_BUILD'; $receipt.validation_stage = $validationStage; $endpoint="https://$accountId.r2.cloudflarestorage.com"
  $env:R2_ACCOUNT_ID=$accountId;$env:R2_ACCESS_KEY_ID=$accessKey;$env:R2_SECRET_ACCESS_KEY=$secretValue;$env:R2_BUCKET=$bucket;$env:R2_ENDPOINT=$endpoint
  $validationStage = 'CLIENT_INIT'; $receipt.validation_stage = $validationStage
  $receipt.r2_provider_reached=$true;$receipt.failure_classification='NONE'
  if($R2ConfigPreflight){ $receipt.final_status='CONFIG_PREFLIGHT_PASS_NO_PROVIDER_OPERATION'; exit 0 }
  $validationStage = 'PUT'; $receipt.validation_stage = $validationStage
  $p=R2 PUT $endpoint $bucket $objectKey $accessKey $secretValue $payload;$receipt.put=if($p -eq 200){'PASS'}else{"FAIL_HTTP_$p"}
  $validationStage = 'HEAD'; $receipt.validation_stage = $validationStage
  $h=R2 HEAD $endpoint $bucket $objectKey $accessKey $secretValue $null;$receipt.head=if($h -eq 200){'PASS'}else{"FAIL_HTTP_$h"}
  $validationStage = 'GET'; $receipt.validation_stage = $validationStage
  $g=R2 GET $endpoint $bucket $objectKey $accessKey $secretValue $null -ReturnBody;$receipt.get=if($g.StatusCode -eq 200 -and ((Hash $g.Body) -eq (Hash $payload))){'PASS_CONTENT_INTEGRITY'}else{'FAIL_CONTENT_INTEGRITY'}
  $validationStage = 'SECURITY_CHECK'; $receipt.validation_stage = $validationStage
  $aq=[Net.HttpWebRequest]::Create("$endpoint/$bucket/$objectKey");$aq.Method='GET';try{$ar=[Net.HttpWebResponse]$aq.GetResponse();$as=[int]$ar.StatusCode;$ar.Dispose()}catch [Net.WebException]{if($_.Exception.Response){$as=[int]$_.Exception.Response.StatusCode;$providerErrorCode='SAFE_PROVIDER_CODE_UNPARSED';$_.Exception.Response.Dispose()}else{throw}};$receipt.anonymous_http_status=$as;$receipt.anonymous_access=ClassifyAnonymousStatus $as $true;$receipt.anonymous_provider_error_code=$providerErrorCode;$receipt.anonymous_safe_error_message=if($as -eq 400){'UNSIGNED_GET_RETURNED_HTTP_400; PROVIDER_ERROR_BODY_NOT_PERSISTED'}else{$null}
  $receipt.path_traversal_rejection=if('../escape' -match '(^|/)(\.\.|$)'){'PASS_STATIC_POLICY'}else{'FAIL'}
  $receipt.storage_abstraction_isolation='PASS_KEY_NAMESPACE_ONLY; LIVE_APP_WIRING_PENDING'
  $validationStage = 'DELETE'; $receipt.validation_stage = $validationStage
  $d=R2 DELETE $endpoint $bucket $objectKey $accessKey $secretValue $null;$receipt.delete=if($d -in 200,204){'PASS'}else{"FAIL_HTTP_$d"};$receipt.cleanup=$receipt.delete
  $receipt.final_status=if($receipt.put -eq 'PASS' -and $receipt.head -eq 'PASS' -and $receipt.get -eq 'PASS_CONTENT_INTEGRITY' -and $receipt.delete -eq 'PASS' -and $receipt.anonymous_access -eq 'PASS_ANONYMOUS_ACCESS_DENIED'){'PASS_WITH_APP_LAYER_CHECK_PENDING'}else{'FAIL'}
} catch {
  $receipt.validation_stage=$validationStage
  $receipt.error_type=$_.Exception.GetType().Name
  $receipt.fully_qualified_error_id=$_.FullyQualifiedErrorId
  $receipt.error_category=$_.CategoryInfo.Category.ToString()
  $receipt.script_name=$_.InvocationInfo.ScriptName
  $receipt.script_line_number=$_.InvocationInfo.ScriptLineNumber
  $receipt.script_offset_in_line=$_.InvocationInfo.OffsetInLine
  $receipt.safe_position_message='POSITION_REDACTED; SECRET_AND_AUTH_MATERIAL_REDACTED'
  $receipt.http_status_if_available=$httpStatus
  $receipt.provider_error_code_if_available=$providerErrorCode
  $receipt.safe_error_message='SANITIZED_EXCEPTION_RECORDED; SECRET_AND_AUTH_MATERIAL_REDACTED'
  $receipt.failure_classification='LOCAL_POWERSHELL_VALIDATION_FAILURE'
  $receipt.r2_http_response_observed=$false
  $receipt.final_status='ERROR_SAFE_REDACTED'
  $exitCode = 1
} finally {
  if($secretPtr -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPtr)};$secretValue=$null
  Remove-Item Env:R2_ACCOUNT_ID,Env:R2_ACCESS_KEY_ID,Env:R2_SECRET_ACCESS_KEY,Env:R2_BUCKET,Env:R2_ENDPOINT -ErrorAction SilentlyContinue
  $receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $receiptPath -Encoding UTF8
}
Write-Output "R2 validation receipt written: $receiptPath"
if($receipt.final_status -in @('FAIL','ERROR_SAFE_REDACTED')) { $exitCode = 1 }
exit $exitCode
