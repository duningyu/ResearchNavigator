[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
  & cloudflared --version
  exit $LASTEXITCODE
}
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
  throw 'cloudflared is not installed and winget is unavailable.'
}
& winget install --id Cloudflare.cloudflared --exact --accept-source-agreements --accept-package-agreements
if ($LASTEXITCODE -ne 0) { throw "cloudflared installation failed with exit code $LASTEXITCODE" }
