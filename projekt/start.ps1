param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath 'backend/.venv/Scripts/python.exe')) { throw 'Najpierw uruchom .\setup.ps1' }
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Brak interfejsu. Uruchom .\setup.ps1' }
Write-Host "EZI: http://127.0.0.1:$Port — Ctrl+C kończy pracę." -ForegroundColor Green
& ./backend/.venv/Scripts/python.exe -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port $Port
