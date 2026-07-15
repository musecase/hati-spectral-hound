$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
$Python = if (Test-Path -LiteralPath $VenvPython) {
    Get-Item -LiteralPath $VenvPython
} else {
    Get-ChildItem -Path $PythonRoot -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch "WindowsApps" } |
        Sort-Object FullName -Descending |
        Select-Object -First 1
}

if (-not $Python) {
    throw "Python 3.11 or newer was not found beneath $PythonRoot"
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
Push-Location $ProjectRoot
try {
    & $Python.FullName -m unittest discover -s tests -v
}
finally {
    Pop-Location
}
