param([int]$Port = 8768)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Ambiente Python ausente. Consulte a instalacao no README.md.'
}
Set-Location -LiteralPath $projectRoot
Write-Host "ModuPDF: http://127.0.0.1:$Port"
& $pythonPath -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
