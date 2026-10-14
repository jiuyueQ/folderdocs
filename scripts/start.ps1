param([ValidateRange(1024,65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts\setup.ps1 first.' }
Push-Location $projectRoot
$workerProcess = $null
try {
    & $pythonPath manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    & $pythonPath manage.py collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Static asset collection failed.' }
    $logRoot = if ($env:FOLDERDOCS_DATA_DIR) { $env:FOLDERDOCS_DATA_DIR } else { Join-Path $projectRoot 'data' }
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $workerProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-u', 'manage.py', 'worker') -WorkingDirectory $projectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'worker.log') -RedirectStandardError (Join-Path $logRoot 'worker-error.log')
    Write-Host "Open http://127.0.0.1:$Port and create your account. Ctrl+C stops both services."
    & $pythonPath serve.py --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Web service stopped with an error. Check whether the port is in use.' }
} finally {
    if ($workerProcess -and -not $workerProcess.HasExited) { Stop-Process -Id $workerProcess.Id }
    Pop-Location
}
