$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CredentialPath = Join-Path $ProjectRoot "config\openai-api-key.clixml"

$Credential = Get-Credential `
    -UserName "OPENAI_API_KEY" `
    -Message "Paste the HATI project API key into the Password field. Do not paste it into chat."
if (-not $Credential) {
    throw "API key entry was cancelled."
}

$Credential | Export-Clixml -LiteralPath $CredentialPath
Write-Host "Saved the OpenAI API key in an encrypted, Windows-user-bound file:"
Write-Host $CredentialPath
Write-Host "The key is not stored as plaintext and the file is ignored by Git."
