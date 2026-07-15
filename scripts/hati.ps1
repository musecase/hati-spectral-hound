param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$HatiArguments
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$CredentialPath = Join-Path $ProjectRoot "config\camera-credential.clixml"
$OpenAIKeyPath = Join-Path $ProjectRoot "config\openai-api-key.clixml"
$TelegramCredentialPath = Join-Path $ProjectRoot "config\telegram-credential.clixml"
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
$NeedsCameraCredential = (
    $HatiArguments.Count -gt 0 -and
    $HatiArguments[0] -in @("camera-probe", "watch")
)
if ($NeedsCameraCredential -and (Test-Path -LiteralPath $CredentialPath)) {
    $CameraCredential = Import-Clixml -LiteralPath $CredentialPath
    $env:HATI_CAMERA_USERNAME = $CameraCredential.UserName
    $env:HATI_CAMERA_PASSWORD = $CameraCredential.GetNetworkCredential().Password
}
$NeedsOpenAIKey = (
    $HatiArguments.Count -gt 0 -and
    $HatiArguments[0] -eq "classify-event"
)
if ($NeedsOpenAIKey -and (Test-Path -LiteralPath $OpenAIKeyPath)) {
    $OpenAICredential = Import-Clixml -LiteralPath $OpenAIKeyPath
    $env:OPENAI_API_KEY = $OpenAICredential.GetNetworkCredential().Password
}
$NeedsTelegramCredential = (
    $HatiArguments.Count -gt 0 -and
    $HatiArguments[0] -in @("telegram-notify", "telegram-poll-once")
)
if ($NeedsTelegramCredential -and (Test-Path -LiteralPath $TelegramCredentialPath)) {
    $TelegramCredential = Import-Clixml -LiteralPath $TelegramCredentialPath
    $env:HATI_TELEGRAM_CHAT_ID = $TelegramCredential.UserName
    $env:HATI_TELEGRAM_BOT_TOKEN = $TelegramCredential.GetNetworkCredential().Password
}
Push-Location $ProjectRoot
$ExitCode = 1
try {
    & $Python.FullName -m hati @HatiArguments
    $ExitCode = $LASTEXITCODE
}
finally {
    Remove-Item Env:HATI_CAMERA_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:HATI_CAMERA_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:HATI_TELEGRAM_CHAT_ID -ErrorAction SilentlyContinue
    Remove-Item Env:HATI_TELEGRAM_BOT_TOKEN -ErrorAction SilentlyContinue
    Pop-Location
}
exit $ExitCode
