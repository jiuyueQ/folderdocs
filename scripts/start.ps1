param([ValidateRange(1024,65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts\setup.ps1 first.' }
Push-Location $projectRoot
$workerProcess = $null
$webProcess = $null
$instanceLock = $null
try {
    $logRoot = if ($env:FOLDERDOCS_DATA_DIR) { $env:FOLDERDOCS_DATA_DIR } else { Join-Path $projectRoot 'data' }
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    try {
        $instanceLock = [System.IO.File]::Open((Join-Path $logRoot '.instance-lock'), [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    } catch { throw 'FolderDocs is already running for this data directory. Close the existing launcher first.' }
    & $pythonPath manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    & $pythonPath manage.py collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Static asset collection failed.' }
    $workerProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-u', 'manage.py', 'worker') -WorkingDirectory $projectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'worker.log') -RedirectStandardError (Join-Path $logRoot 'worker-error.log')
    Write-Host "Open http://127.0.0.1:$Port and create your account. Ctrl+C stops both services."
    $webProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-u', 'serve.py', '--port', $Port) -WorkingDirectory $projectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'web.log') -RedirectStandardError (Join-Path $logRoot 'web-error.log')
    while (-not $webProcess.HasExited) { Start-Sleep -Milliseconds 250 }
    if ($webProcess.ExitCode -ne 0) { throw 'Web service stopped with an error. Check data\web-error.log and whether the port is in use.' }
} finally {
    foreach ($ownedProcess in @($webProcess, $workerProcess)) {
        if ($ownedProcess -and -not $ownedProcess.HasExited) { & taskkill.exe /PID $ownedProcess.Id /T /F | Out-Null }
    }
    if ($instanceLock) { $instanceLock.Dispose() }
    Pop-Location
}
