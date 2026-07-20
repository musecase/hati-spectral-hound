$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExitCode = 0
$Output = Join-Path $ProjectRoot "data\camera_probe\latest.jpg"

Write-Host "Testing one authenticated camera image."
Write-Host "This does not call the model and cannot operate the diffuser."
Write-Host ""

try {
    & (Join-Path $PSScriptRoot "hati.ps1") `
        camera-probe `
        --config (Join-Path $ProjectRoot "config\hati.local.json") `
        --output $Output
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -eq 0) {
        Write-Host ""
        Write-Host "Camera image saved at:"
        Write-Host $Output
    }
}
catch {
    $ExitCode = 1
    Write-Host ""
    Write-Host "Camera probe failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message
}
finally {
    Write-Host ""
    Read-Host "Press Enter to close"
}

exit $ExitCode
