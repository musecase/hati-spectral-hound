$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BasePython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$CacheRoot = Join-Path $ProjectRoot ".cache"
$env:PIP_CACHE_DIR = Join-Path $CacheRoot "pip"
$env:TEMP = Join-Path $CacheRoot "tmp"
$env:TMP = $env:TEMP

New-Item -ItemType Directory -Force -Path $env:PIP_CACHE_DIR, $env:TEMP | Out-Null

if (-not (Test-Path -LiteralPath $BasePython)) {
    throw "Python 3.12 was not found at $BasePython"
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $BasePython -m venv (Join-Path $ProjectRoot ".venv")
}

& $VenvPython -m pip install --disable-pip-version-check -e $ProjectRoot
