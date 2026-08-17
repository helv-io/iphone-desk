@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating .venv ...
    py -3.12 -m venv .venv
    if errorlevel 1 py -3 -m venv .venv
    if errorlevel 1 (
        echo Python 3.12+ is required. Install it from https://www.python.org/downloads/
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -e ".[dev]"
)

".venv\Scripts\python.exe" -m iphone_desk %*
