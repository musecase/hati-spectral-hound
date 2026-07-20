$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExitCode = 0

Write-Host "Starting the HATI Telegram operator link."
Write-Host "Press Ctrl+C to stop it safely."
Write-Host ""

try {
    & (Join-Path $PSScriptRoot "hati.ps1") `
        telegram-poll `
        --config (Join-Path $ProjectRoot "config\hati.local.json") `
        --state (Join-Path $ProjectRoot "data\runtime\telegram-offset.json")
    $ExitCode = $LASTEXITCODE
}
catch {
    $ExitCode = 1
    Write-Host ""
    Write-Host "Telegram operator link failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message
}
finally {
    Write-Host ""
    Read-Host "Press Enter to close"
}

exit $ExitCode
