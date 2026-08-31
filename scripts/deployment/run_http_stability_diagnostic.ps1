[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [double] $DurationMinutes = 15,
  [int] $IntervalSeconds = 45,
  [string] $OutputPath
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd('\')
$state=Get-Content (Join-Path $root 'deployment/public_demo_state.json') -Raw | ConvertFrom-Json
if(-not $OutputPath){$OutputPath=Join-Path $root 'deployment/http_stability/HTTP_STABILITY_DIAGNOSTIC.csv'}
New-Item -ItemType Directory -Path (Split-Path -Parent $OutputPath) -Force | Out-Null
$rows=[Collections.Generic.List[object]]::new(); $started=[DateTimeOffset]::UtcNow; $deadline=$started.AddMinutes($DurationMinutes); $attempt=0
while([DateTimeOffset]::UtcNow -lt $deadline){
  $attempt++
  $local=''; $worker=''; $cloud=''
  try{$local=if((Invoke-WebRequest -Uri "http://127.0.0.1:$([int]$state.api_port)/api/health" -UseBasicParsing -TimeoutSec 15).StatusCode -ge 200){'ONLINE'}else{'OFFLINE'}}catch{$local='OFFLINE'}
  $worker='OFFLINE'; $cloud='OFFLINE'
  $wp=Get-Process -Id ([int]$state.worker_process.pid) -ErrorAction SilentlyContinue
  if($wp -and [Math]::Abs(([DateTimeOffset]$wp.StartTime.ToUniversalTime()).Subtract(([DateTimeOffset]$state.worker_process.creation_time_utc).ToUniversalTime()).TotalMilliseconds) -le 10){$worker='ONLINE'}
  $cp=Get-Process -Id ([int]$state.cloudflared_process.pid) -ErrorAction SilentlyContinue
  if($cp -and [Math]::Abs(([DateTimeOffset]$cp.StartTime.ToUniversalTime()).Subtract(([DateTimeOffset]$state.cloudflared_process.creation_time_utc).ToUniversalTime()).TotalMilliseconds) -le 10){$cloud='ONLINE'}
  foreach($target in @([pscustomobject]@{name='LOCAL_API';url="http://127.0.0.1:$([int]$state.api_port)/api/health"},[pscustomobject]@{name='TUNNEL';url="$($state.tunnel_origin)/api/health"},[pscustomobject]@{name='VERCEL';url="$($state.vercel_origin)/"})){
    $sw=[Diagnostics.Stopwatch]::StartNew(); $result='FAIL'; $status=$null; $type=''; $category='TRANSPORT_LAYER_FAILURE'
    try{$status=[int](Invoke-WebRequest -Uri $target.url -UseBasicParsing -TimeoutSec 15).StatusCode; $result='PASS'; $category='HTTP_RESPONSE'}catch{$type=$_.Exception.GetType().Name; if($type -eq 'TaskCanceledException'){$category='CLIENT_TIMEOUT'}else{$category='TRANSPORT_LAYER_FAILURE'}}finally{$sw.Stop()}
    $rows.Add([pscustomobject]@{timestamp=[DateTimeOffset]::UtcNow.ToString('o');target=$target.name;attempt_number=$attempt;result=$result;http_status=$status;duration_ms=$sw.ElapsedMilliseconds;exception_type=$type;exception_category=$category;local_api_status=$local;worker_status=$worker;cloudflared_status=$cloud})
  }
  $rows | Export-Csv -LiteralPath $OutputPath -NoTypeInformation -Encoding utf8
  $remaining=$deadline.Subtract([DateTimeOffset]::UtcNow).TotalSeconds; if($remaining -le 0){break}; Start-Sleep -Seconds ([Math]::Min($IntervalSeconds,[int]$remaining))
}
Write-Output "HTTP_STABILITY_DIAGNOSTIC_COMPLETE attempts=$attempt output=$OutputPath"
