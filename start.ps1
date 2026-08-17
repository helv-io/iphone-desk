# Launch iPhone Desk. Finds Python 3.12+ without requiring `py -3.12`.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Test-Python312([string]$Exe) {
    if (-not $Exe -or -not (Test-Path $Exe)) {
        return $false
    }
    try {
        $code = & $Exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Find-SystemPython {
    $tried = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

    foreach ($cmd in @("py")) {
        $py = Get-Command $cmd -ErrorAction SilentlyContinue
        if (-not $py) { continue }
        foreach ($arg in @("-3.12", "-3.13", "-3.14", "-3")) {
            try {
                $exe = & $py.Source $arg -c "import sys; print(sys.executable)" 2>$null
                if ($exe -and $tried.Add($exe.Trim()) -and (Test-Python312 $exe.Trim())) {
                    return $exe.Trim()
                }
            } catch {
            }
        }
    }

    foreach ($name in @("python", "python3")) {
        $hit = Get-Command $name -ErrorAction SilentlyContinue
        if ($hit -and $tried.Add($hit.Source) -and (Test-Python312 $hit.Source)) {
            return $hit.Source
        }
    }

    $uvRoots = @(
        (Join-Path $env:APPDATA "uv\python"),
        (Join-Path $env:USERPROFILE ".local\share\uv\python")
    )
    foreach ($root in $uvRoots) {
        if (-not (Test-Path $root)) { continue }
        $found = Get-ChildItem -Path $root -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "cpython-3\.(1[2-9]|[2-9]\d)" } |
            Sort-Object FullName -Descending
        foreach ($item in $found) {
            if ($tried.Add($item.FullName) -and (Test-Python312 $item.FullName)) {
                return $item.FullName
            }
        }
    }

    throw "Python 3.12+ is required. Install it from https://www.python.org/downloads/ or: uv python install 3.12"
}

function Stop-RunningDesk {
    $repo = [regex]::Escape($PSScriptRoot)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match '^python(\.exe)?$' -and
        $_.CommandLine -and
        $_.CommandLine -match 'iphone_desk' -and
        $_.CommandLine -match $repo
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating .venv ..."
    $systemPython = Find-SystemPython
    & $systemPython -m venv (Join-Path $PSScriptRoot ".venv")
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -e ".[dev]"
}

Stop-RunningDesk
& $venvPython -m iphone_desk @args
