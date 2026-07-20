$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExitCode = 0

Write-Host "HATI will stop after one motion event."
Write-Host "The complete path is camera -> GPT vision -> safety decision -> bounded action -> Telegram."
Write-Host "Current local configuration is disarmed and in test mode unless you deliberately changed it."
Write-Host ""

try {
    & (Join-Path $PSScriptRoot "hati.ps1") `
        run-once `
        --config (Join-Path $ProjectRoot "config\hati.local.json") `
        --snapshot-only `
        --max-samples 2400
    $ExitCode = $LASTEXITCODE
}
catch {
    $ExitCode = 1
    Write-Host ""
    Write-Host "HATI one-event run failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message
}
finally {
    Write-Host ""
    Read-Host "Press Enter to close"
}

exit $ExitCode
