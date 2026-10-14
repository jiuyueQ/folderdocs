$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & '.\.venv\Scripts\python.exe' manage.py migrate
    if ($LASTEXITCODE -ne 0) { throw 'Database setup failed.' }
    & '.\.venv\Scripts\python.exe' manage.py collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Static asset setup failed.' }
    Write-Host 'Setup complete. Run scripts\start.ps1 to start FolderDocs.'
} finally { Pop-Location }
