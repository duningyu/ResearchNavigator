[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ProjectRoot,
  [Parameter(Mandatory)] [uri] $VercelOrigin,
  [int] $ApiPort = 8000,
  [Parameter(Mandatory)] [string] $DemoDataDir
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$DemoDataDir = [IO.Path]::GetFullPath($DemoDataDir)
if (-not ($VercelOrigin.Scheme -eq 'https' -and $VercelOrigin.AbsolutePath -eq '/')) { throw 'VercelOrigin must be an HTTPS origin.' }
if ($DemoDataDir.StartsWith($ProjectRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'DemoDataDir must be outside the repository.' }
New-Item -ItemType Directory -Force -Path $DemoDataDir | Out-Null
$databasePath = Join-Path $DemoDataDir 'research_navigator.db'
$databaseUrlPath = $databasePath.Replace('\', '/')
$statePath = Join-Path $ProjectRoot 'deployment/public_demo_state.json'
$stateDirectory = Split-Path -Parent $statePath
New-Item -ItemType Directory -Force -Path $stateDirectory | Out-Null
$python = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $python)) { throw "Python environment not found: $python" }
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) { throw 'cloudflared is required; run install_cloudflared.ps1 first.' }
$env:RN_DATA_DIR = $DemoDataDir
$env:RN_DATABASE_URL = "sqlite+pysqlite:///$databaseUrlPath"
$env:RN_CORS_ALLOWED_ORIGINS = $VercelOrigin.AbsoluteUri.TrimEnd('/')
$env:RN_ALLOWED_ORIGINS = $env:RN_CORS_ALLOWED_ORIGINS
$env:RN_ENVIRONMENT = 'demo'
Push-Location $ProjectRoot
try {
  & $python -m alembic upgrade head
  if ($LASTEXITCODE -ne 0) { throw 'Alembic migration failed.' }
  $api = Start-Process -FilePath $python -ArgumentList '-m','uvicorn','research_navigator.main:app','--host','127.0.0.1','--port',"$ApiPort" -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden
  $worker = Start-Process -FilePath $python -ArgumentList '-m','services.worker.main','--poll-seconds','2' -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden
  $deadline = (Get-Date).AddSeconds(45)
  do {
    try { $health = Invoke-WebRequest "http://127.0.0.1:$ApiPort/api/health" -UseBasicParsing -TimeoutSec 3; if ($health.StatusCode -eq 200) { break } } catch {}
    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $deadline)
  if (-not $health -or $health.StatusCode -ne 200) { throw 'Local API health did not become ready.' }
  $tunnel = Start-Process -FilePath 'cloudflared' -ArgumentList 'tunnel','--url',"http://127.0.0.1:$ApiPort" -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $DemoDataDir 'cloudflared.stdout.log') -RedirectStandardError (Join-Path $DemoDataDir 'cloudflared.stderr.log')
  $tunnelUrl = $null
  $deadline = (Get-Date).AddSeconds(45)
  do {
    if (Test-Path (Join-Path $DemoDataDir 'cloudflared.stderr.log')) { $tunnelUrl = Select-String -Path (Join-Path $DemoDataDir 'cloudflared.stderr.log') -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1 -ExpandProperty Matches | ForEach-Object Value }
    if (-not $tunnelUrl) { Start-Sleep -Milliseconds 500 }
  } while (-not $tunnelUrl -and (Get-Date) -lt $deadline)
  if (-not $tunnelUrl) { throw 'Quick Tunnel URL was not observed.' }
  $shareUrl = "$($VercelOrigin.AbsoluteUri.TrimEnd('/'))/?rn_backend=$([uri]::EscapeDataString($tunnelUrl))"
  $state = [ordered]@{ version = '2.2.3'; source_commit = (& git rev-parse HEAD).Trim(); deployment_revision = 'RN223_PUBLIC_DEMO_DEPLOYMENT_V1'; vercel_origin = $VercelOrigin.AbsoluteUri.TrimEnd('/'); tunnel_origin = $tunnelUrl; api_port = $ApiPort; api_pid = $api.Id; worker_pid = $worker.Id; cloudflared_pid = $tunnel.Id; demo_data_dir = $DemoDataDir; share_url = $shareUrl; started_at = (Get-Date).ToUniversalTime().ToString('o'); cloudflare_tunnel_type = 'QUICK_TUNNEL'; random_hostname = $true; sla = 'none' }
  $state | ConvertTo-Json | Set-Content $statePath -Encoding utf8
  Write-Output $shareUrl
} finally { Pop-Location }
