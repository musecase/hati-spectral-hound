$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CredentialPath = Join-Path $ProjectRoot "config\camera-credential.clixml"

try {
    $Credential = Import-Clixml -LiteralPath $CredentialPath
    $PlainPassword = $Credential.GetNetworkCredential().Password
    Write-Host "Saved HATI camera username: $($Credential.UserName)"
    Write-Host "Saved HATI camera password: $PlainPassword" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to clear this window"
}
finally {
    $PlainPassword = $null
    $Credential = $null
    Clear-Host
}
