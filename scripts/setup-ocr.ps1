param([string]$CondaCommand = 'conda')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$ocrPrefix = Join-Path $projectRoot '.tools\ocr'
& $CondaCommand create --prefix $ocrPrefix --override-channels --channel conda-forge --yes tesseract
if ($LASTEXITCODE -ne 0) { throw 'OCR installation failed. Alternatively install Tesseract and set TESSERACT_CMD.' }
$ocrBinary = Join-Path $ocrPrefix 'Library\bin\tesseract.exe'
& $ocrBinary --version
if ($LASTEXITCODE -ne 0) { throw 'OCR binary could not be launched.' }
Write-Host 'OCR ready. FolderDocs detects this installation automatically.'
