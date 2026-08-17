$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv ..."
    try {
        py -3.12 -m venv .venv
    } catch {
        py -3 -m venv .venv
    }
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip
    & ".venv\Scripts\python.exe" -m pip install -e ".[dev]"
}

& ".venv\Scripts\python.exe" -m iphone_desk @args
