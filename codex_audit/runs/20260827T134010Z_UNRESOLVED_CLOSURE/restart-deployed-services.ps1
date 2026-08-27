$ErrorActionPreference = 'Stop'
$projectRoot = 'E:\AI_Projects\ResearchNavigator'
$pythonExe = 'E:\AI_Projects\ResearchNavigator\.venv\Scripts\python.exe'
$runRoot = 'E:\AI_Projects\ResearchNavigator\codex_audit\runs\20260827T134010Z_UNRESOLVED_CLOSURE'

# These parent PIDs were resolved from Win32_Process and all point to this project.
Stop-Process -Id 35552, 33760, 42104 -Force
Start-Sleep -Seconds 2

$api = Start-Process -FilePath $pythonExe -ArgumentList @(
    '-m', 'uvicorn', 'research_navigator.main:app', '--app-dir', 'apps/api',
    '--host', '127.0.0.1', '--port', '8000'
) -WorkingDirectory $projectRoot -WindowStyle Hidden `
    -RedirectStandardOutput "$runRoot\deployed-api.stdout.log" `
    -RedirectStandardError "$runRoot\deployed-api.stderr.log" -PassThru

$worker = Start-Process -FilePath $pythonExe -ArgumentList @(
    '-m', 'services.worker.main', '--poll-seconds', '2'
) -WorkingDirectory $projectRoot -WindowStyle Hidden `
    -RedirectStandardOutput "$runRoot\deployed-worker.stdout.log" `
    -RedirectStandardError "$runRoot\deployed-worker.stderr.log" -PassThru

$web = Start-Process -FilePath $pythonExe -ArgumentList @(
    '-m', 'http.server', '8080', '--bind', '127.0.0.1', '--directory', 'apps/web/dist'
) -WorkingDirectory $projectRoot -WindowStyle Hidden `
    -RedirectStandardOutput "$runRoot\deployed-web.stdout.log" `
    -RedirectStandardError "$runRoot\deployed-web.stderr.log" -PassThru

"api_pid=$($api.Id) worker_pid=$($worker.Id) web_pid=$($web.Id)"
for ($attempt = 1; $attempt -le 10; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 3
        $webStatus = (
            Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8080' -TimeoutSec 3
        ).StatusCode
        "DEPLOYED health=$($health.status) version=$($health.version) web=$webStatus attempt=$attempt"
        exit 0
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

Get-Content -Tail 50 "$runRoot\deployed-api.stderr.log" -ErrorAction SilentlyContinue
exit 1
