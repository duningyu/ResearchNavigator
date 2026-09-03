[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [switch]$Once,
    [int]$IntervalSeconds = 30
)

$ErrorActionPreference = 'Stop'
$stateDir = Join-Path $ProjectRoot 'deployment\cloud\wsl'
$statePath = Join-Path $stateDir 'WSL_INSTALL_MONITOR_STATE.json'
$logPath = Join-Path $stateDir 'WSL_INSTALL_MONITOR.log'
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

function Get-WslSnapshot {
    $statusText = (& wsl.exe --status 2>&1 | Out-String).Trim()
    $listText = ((& wsl.exe --list --verbose 2>&1 | Out-String) -replace "`0", '').Trim()
    $onlineText = (& wsl.exe --list --online 2>&1 | Out-String).Trim()
    $ubuntuLine = ($listText -split "`r?`n" | Where-Object { $_ -match '(?i)Ubuntu' -and $_ -notmatch 'docker-desktop' } | Select-Object -First 1)
    $ubuntuRegistered = [bool]$ubuntuLine
    $ubuntuState = $null
    $ubuntuVersion = $null
    if ($ubuntuLine) {
        $normalized = ($ubuntuLine -replace "`0", '').Trim()
        if ($normalized -match '(?i)Ubuntu\s+(?<state>Running|Stopped)\s+(?<version>[12])') {
            $ubuntuState = $Matches.state
            $ubuntuVersion = [int]$Matches.version
        }
    }
    $installer = @(Get-CimInstance Win32_Process -Filter "Name = 'wsl.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match '(?i)--install\s+-d\s+Ubuntu' })
    $rebootRequired = ($statusText -match '(?i)restart|reboot|required')
    $classification = if ($rebootRequired) { 'INSTALL_COMPLETED_REBOOT_REQUIRED' }
        elseif ($ubuntuRegistered -and $installer.Count -gt 0) { 'UBUNTU_REGISTERED_INSTALLER_STILL_RUNNING' }
        elseif ($ubuntuRegistered) { 'INSTALL_COMPLETED' }
        elseif ($installer.Count -gt 0) { 'INSTALL_RUNNING' }
        else { 'MONITOR_ERROR' }
    [ordered]@{
        checked_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        installer_process_present = ($installer.Count -gt 0)
        installer_pid = if ($installer.Count -gt 0) { [int]$installer[0].ProcessId } else { $null }
        ubuntu_registered = $ubuntuRegistered
        ubuntu_state = $ubuntuState
        ubuntu_wsl_version = $ubuntuVersion
        docker_desktop_present = [bool]($listText -match '(?i)docker-desktop')
        reboot_required = $rebootRequired
        classification = $classification
        next_action = switch ($classification) {
            'INSTALL_RUNNING' { 'Wait for the existing installer; do not start another.'; break }
            'UBUNTU_REGISTERED_INSTALLER_STILL_RUNNING' { 'Complete the existing Ubuntu first-run setup; do not start another installer.'; break }
            'INSTALL_COMPLETED' { 'Initialize Ubuntu interactively if first-run setup is pending.'; break }
            'INSTALL_COMPLETED_REBOOT_REQUIRED' { 'Restart Windows manually, then resume from disk.'; break }
            default { 'Inspect WSL status and installer evidence; do not retry automatically.' }
        }
    }
}

do {
    try {
        $snapshot = Get-WslSnapshot
        $json = $snapshot | ConvertTo-Json -Depth 4
        Set-Content -LiteralPath $statePath -Value $json -Encoding utf8
        Add-Content -LiteralPath $logPath -Value ("{0} {1}" -f $snapshot.checked_at_utc, $snapshot.classification)
        $json
    } catch {
        $failure = [ordered]@{
            checked_at_utc = (Get-Date).ToUniversalTime().ToString('o')
            installer_process_present = $null
            installer_pid = $null
            ubuntu_registered = $null
            ubuntu_state = $null
            ubuntu_wsl_version = $null
            docker_desktop_present = $null
            reboot_required = $null
            classification = 'MONITOR_ERROR'
            next_action = 'Inspect monitor error; do not install or unregister a distro.'
        }
        $failure | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding utf8
        Add-Content -LiteralPath $logPath -Value ("{0} MONITOR_ERROR" -f $failure.checked_at_utc)
        $failure | ConvertTo-Json -Depth 4
    }
    if (-not $Once) { Start-Sleep -Seconds ([Math]::Max(30, $IntervalSeconds)) }
} while (-not $Once)
