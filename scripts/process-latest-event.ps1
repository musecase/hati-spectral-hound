$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EventRoot = Join-Path $ProjectRoot "data\events"
$ExitCode = 0

try {
    $EventPath = Get-ChildItem -LiteralPath $EventRoot -Filter "event.json" -File -Recurse |
        Sort-Object LastWriteTime -Descending |
        Where-Object {
            try {
                (Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json).processing_state `
                    -eq "captured"
            }
            catch {
                $false
            }
        } |
        Select-Object -First 1
    if (-not $EventPath) {
        throw "No unclassified captured event was found."
    }

    Write-Host "Processing: $($EventPath.FullName)"
    Write-Host "This resumes the event through vision, decision, bounded actuation, and Telegram."
    Write-Host "The local defaults are disarmed and in test mode."
    Write-Host ""

    & (Join-Path $PSScriptRoot "hati.ps1") `
        process-event `
        --config (Join-Path $ProjectRoot "config\hati.local.json") `
        --event $EventPath.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Event pipeline failed with exit code $LASTEXITCODE."
    }
}
catch {
    $ExitCode = 1
    Write-Host ""
    Write-Host "Event processing failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message
}
finally {
    Write-Host ""
    Read-Host "Press Enter to close"
}

exit $ExitCode
