$ErrorActionPreference = 'Continue'
$logPath = 'E:\AI_Projects\ResearchNavigator\codex_audit\runs\20260827T134010Z_UNRESOLVED_CLOSURE\wsl-install-elevated.log'
"started=$(Get-Date -Format o)" | Set-Content -LiteralPath $logPath -Encoding utf8
wsl.exe --install --no-distribution *>&1 | Add-Content -LiteralPath $logPath -Encoding utf8
"wsl_exit=$LASTEXITCODE" | Add-Content -LiteralPath $logPath -Encoding utf8
Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux | Format-List FeatureName,State | Out-String | Add-Content -LiteralPath $logPath -Encoding utf8
Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform | Format-List FeatureName,State | Out-String | Add-Content -LiteralPath $logPath -Encoding utf8
"finished=$(Get-Date -Format o)" | Add-Content -LiteralPath $logPath -Encoding utf8
exit $LASTEXITCODE
