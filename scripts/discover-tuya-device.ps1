param(
    [string]$DeviceName
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CredentialPath = Join-Path $ProjectRoot "config\tuya-cloud-credential.clixml"
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$DiscoveryScript = Join-Path $PSScriptRoot "discover-tuya-device.py"

if (-not (Test-Path -LiteralPath $CredentialPath)) {
    throw "Tuya cloud credential vault not found. Run save-tuya-cloud-credential.ps1 first."
}
if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "HATI Python environment not found. Run setup.ps1 first."
}

$Credential = Import-Clixml -LiteralPath $CredentialPath
$DeviceName = if ($DeviceName) { $DeviceName } else { Read-Host "Smart Life device name" }
if (-not $DeviceName) {
    throw "Smart Life device name cannot be blank."
}
$env:HATI_TUYA_ACCESS_ID = $Credential.UserName
$env:HATI_TUYA_ACCESS_SECRET = $Credential.GetNetworkCredential().Password
$env:HATI_TUYA_DEVICE_NAME = $DeviceName

try {
    & $PythonPath $DiscoveryScript
    if ($LASTEXITCODE -ne 0) {
        throw "Tuya discovery exited with code $LASTEXITCODE."
    }
}
finally {
    Remove-Item Env:HATI_TUYA_ACCESS_ID -ErrorAction SilentlyContinue
    Remove-Item Env:HATI_TUYA_ACCESS_SECRET -ErrorAction SilentlyContinue
    Remove-Item Env:HATI_TUYA_DEVICE_NAME -ErrorAction SilentlyContinue
}
