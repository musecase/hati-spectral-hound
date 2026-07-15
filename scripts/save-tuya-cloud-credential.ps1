$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CredentialPath = Join-Path $ProjectRoot "config\tuya-cloud-credential.clixml"

$Credential = Get-Credential -Message "Tuya project credentials: username = Access ID/Client ID; password = Access Secret/Client Secret"
if (-not $Credential) {
    throw "Credential entry was cancelled."
}

$Credential | Export-Clixml -LiteralPath $CredentialPath
Write-Host "Saved the Tuya project credential in an encrypted, Windows-user-bound file:"
Write-Host $CredentialPath
Write-Host "The values are not stored as plaintext and the file is ignored by Git."
