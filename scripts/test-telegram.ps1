$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExitCode = 0

try {
    & (Join-Path $PSScriptRoot "hati.ps1") `
        telegram-poll-once `
        --config (Join-Path $ProjectRoot "config\hati.local.json")
    if ($LASTEXITCODE -ne 0) {
        throw "HATI Telegram test exited with code $LASTEXITCODE."
    }
}
catch {
    $ExitCode = 1
    Write-Host ""
    Write-Host "Telegram smoke test failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message
}
finally {
    Write-Host ""
    Read-Host "Press Enter to close"
}

exit $ExitCode
