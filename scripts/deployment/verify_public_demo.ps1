[CmdletBinding()]
param([Parameter(Mandatory)] [string] $ProjectRoot)
$ErrorActionPreference = 'Stop'
$state = Get-Content (Join-Path (Resolve-Path $ProjectRoot) 'deployment/public_demo_state.json') -Raw | ConvertFrom-Json
$local = Invoke-WebRequest "http://127.0.0.1:$($state.api_port)/api/health" -UseBasicParsing
$public = Invoke-WebRequest "$($state.tunnel_origin)/api/health" -UseBasicParsing
$frontend = Invoke-WebRequest $state.vercel_origin -UseBasicParsing
if ($local.StatusCode -ne 200 -or $public.StatusCode -ne 200 -or $frontend.StatusCode -ne 200) { throw 'Public demo readiness verification failed.' }
Write-Output ([ordered]@{ local_api = $local.StatusCode; tunnel_api = $public.StatusCode; vercel_frontend = $frontend.StatusCode; tunnel_origin = $state.tunnel_origin } | ConvertTo-Json)
