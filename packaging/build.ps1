# Build dist/iPhoneDesk.exe (one-file, no console).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv. Run start.ps1 once, or: py -3.12 -m venv .venv"
}

& $python -m pip install -e ".[dist]"
if ($LASTEXITCODE -ne 0) { throw "pip install [dist] failed" }

$spec = Join-Path $Root "packaging\iphone-desk.spec"
& $python -m PyInstaller --noconfirm --clean $spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path $Root "dist\iPhoneDesk.exe"
if (-not (Test-Path $exe)) { throw "Expected $exe" }
$version = & $python -c "from iphone_desk import __version__; print(__version__)"
$named = Join-Path $Root "dist\iPhoneDesk-$version-windows-x64.exe"
Copy-Item $exe $named -Force
Get-Item $named | Format-List FullName, Length, LastWriteTime
Write-Host "Built $named"
