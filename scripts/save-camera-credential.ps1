$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CredentialPath = Join-Path $ProjectRoot "config\camera-credential.clixml"

$Credential = Get-Credential -UserName "hati_viewer" -Message "Enter the local Foscam viewer credential for HATI"
if (-not $Credential) {
    throw "Credential entry was cancelled."
}

$Credential | Export-Clixml -LiteralPath $CredentialPath
Write-Host "Saved an encrypted, Windows-user-bound credential at:"
Write-Host $CredentialPath
Write-Host "The password is not stored as plaintext and the file is ignored by Git."
