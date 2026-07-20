$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EventRoot = Join-Path $ProjectRoot "data\events"
$ReviewRoot = Join-Path $ProjectRoot "data\learning\reviews"
$ExitCode = 0

try {
    $EventPath = Get-ChildItem -LiteralPath $EventRoot -Filter "event.json" -File -Recurse |
        Sort-Object LastWriteTime -Descending |
        Where-Object {
            try {
                @((Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json).feedback).Count -gt 0
            }
            catch {
                $false
            }
        } |
        Select-Object -First 1
    if (-not $EventPath) {
        throw "No reviewed event with owner feedback was found."
    }

    Write-Host "Reviewing feedback for: $($EventPath.FullName)"
    Write-Host "Correct feedback becomes a protected regression case."
    Write-Host "Only conservative false-alarm feedback may propose a candidate."
    Write-Host ""

    & (Join-Path $PSScriptRoot "hati.ps1") `
        review-event-feedback `
        --config (Join-Path $ProjectRoot "config\hati.local.json") `
        --event $EventPath.FullName `
        --output $ReviewRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Feedback review failed with exit code $LASTEXITCODE."
    }

    $Event = Get-Content -Raw -LiteralPath $EventPath.FullName | ConvertFrom-Json
    $ReviewPath = Join-Path $ReviewRoot "$($Event.event_id).json"
    $Review = Get-Content -Raw -LiteralPath $ReviewPath | ConvertFrom-Json
    if ($null -ne $Review.candidate) {
        Write-Host ""
        Write-Host "Evaluating the conservative candidate against protected events..."
        & (Join-Path $PSScriptRoot "hati.ps1") `
            evaluate-vision-improvement `
            --config (Join-Path $ProjectRoot "config\hati.local.json") `
            --candidate $ReviewPath `
            --events $EventRoot `
            --reports (Join-Path $ProjectRoot "data\learning\reports")
        if ($LASTEXITCODE -ne 0) {
            throw "Candidate was rejected or evaluation failed. No policy was promoted."
        }
    }
    else {
        Write-Host ""
        Write-Host "No change was needed. This event now protects known-good behavior."
    }
}
catch {
    $ExitCode = 1
    Write-Host ""
    Write-Host "Learning review stopped safely:" -ForegroundColor Yellow
    Write-Host $_.Exception.Message
}
finally {
    Write-Host ""
    Read-Host "Press Enter to close"
}

exit $ExitCode
