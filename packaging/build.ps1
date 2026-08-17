# Build dist/iPhoneDesk/iPhoneDesk.exe (onedir bundle) and launch it.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^iPhoneDesk\.exe$'
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv. Run start.ps1 once, or: py -3.12 -m venv .venv"
}

& $python -m pip install -e ".[dist]"
if ($LASTEXITCODE -ne 0) { throw "pip install [dist] failed" }

$spec = Join-Path $Root "packaging\iphone-desk.spec"
& $python -m PyInstaller --noconfirm --clean $spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path $Root "dist\iPhoneDesk\iPhoneDesk.exe"
if (-not (Test-Path $exe)) { throw "Expected $exe" }

$version = & $python -c "from iphone_desk import __version__; print(__version__)"
$zip = Join-Path $Root "dist\iPhoneDesk-$version-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $Root "dist\iPhoneDesk\*") -DestinationPath $zip -Force

Get-Item $exe, $zip | Format-List FullName, Length, LastWriteTime
Write-Host "Built $exe"
Write-Host "Launching bundle..."

$proc = Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) -PassThru
Start-Sleep -Seconds 5
if ($proc.HasExited) {
    $log = Join-Path (Split-Path $exe) "iPhoneDesk.log"
    if (Test-Path $log) {
        Write-Host "--- iPhoneDesk.log ---"
        Get-Content $log
    }
    throw "iPhoneDesk.exe exited immediately with code $($proc.ExitCode)"
}
Write-Host "iPhoneDesk.exe is running (pid $($proc.Id))"
