$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $ProjectRoot "config\hati.local.json"
$ExitCode = 1

Write-Host ""
Write-Host "HATI - Spectral Hound" -ForegroundColor Cyan
Write-Host "One runtime watches continuously, classifies, decides, records, and notifies."
Write-Host ""
Write-Host "1. Disarmed - full observation pipeline; diffuser locked out"
Write-Host "2. Armed    - authorized predator events may run the diffuser"
Write-Host ""

$Choice = Read-Host "Choose 1 or 2"
$Mode = if ($Choice -eq "2") { "armed" } else { "disarmed" }
$Arguments = @(
    "supervise",
    "--config", $ConfigPath,
    "--mode", $Mode,
    "--snapshot-only",
    "--retry-seconds", "5"
)

if ($Mode -eq "armed") {
    Write-Host ""
    Write-Host "ARMED MODE" -ForegroundColor Yellow
    Write-Host "An authorized predator consensus can run the diffuser at the configured"
    Write-Host "strength and duration. Press Ctrl+C at any time to stop HATI."
    $Confirmation = Read-Host "Type ARM HATI to continue"
    if ($Confirmation -cne "ARM HATI") {
        Write-Host "Confirmation did not match. HATI was not started." -ForegroundColor Yellow
        Read-Host "Press Enter to close"
        exit 2
    }
    $Arguments += @("--confirm-armed", $Confirmation)
}

Write-Host ""
Write-Host "Starting HATI in $Mode mode. Press Ctrl+C to stop." -ForegroundColor Green
Write-Host ""

try {
    & (Join-Path $PSScriptRoot "hati.ps1") @Arguments
    $ExitCode = $LASTEXITCODE
}
catch {
    $ExitCode = 1
    Write-Host ""
    Write-Host "HATI stopped with an error:" -ForegroundColor Red
    Write-Host $_.Exception.Message
}
finally {
    Write-Host ""
    Read-Host "Press Enter to close"
}

exit $ExitCode
