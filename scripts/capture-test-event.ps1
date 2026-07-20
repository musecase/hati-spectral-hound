$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExitCode = 0

Write-Host "HATI will watch the grass apron at the coop and stop after one motion event."
Write-Host "When it says it is watching, walk once through the camera view."
Write-Host "This captures frames only: no model call and no diffuser."
Write-Host ""

try {
    & (Join-Path $PSScriptRoot "hati.ps1") `
        watch `
        --config (Join-Path $ProjectRoot "config\hati.local.json") `
        --snapshot-only `
        --max-samples 2400
    $ExitCode = $LASTEXITCODE
}
catch {
    $ExitCode = 1
    Write-Host ""
    Write-Host "Camera capture test failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message
}
finally {
    Write-Host ""
    Read-Host "Press Enter to close"
}

exit $ExitCode
