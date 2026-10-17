$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath 'backend/.venv/Scripts/python.exe')) {
    python -m venv backend/.venv
    if ($LASTEXITCODE -ne 0) { throw 'Nie udało się utworzyć środowiska Python.' }
}
& ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Instalacja zależności Python nie powiodła się.' }
npm.cmd --prefix frontend ci
if ($LASTEXITCODE -ne 0) { throw 'Instalacja zależności Node nie powiodła się.' }
npm.cmd --prefix frontend run build
if ($LASTEXITCODE -ne 0) { throw 'Budowanie interfejsu nie powiodło się.' }
Write-Host 'Gotowe. Uruchom: .\start.ps1' -ForegroundColor Green
