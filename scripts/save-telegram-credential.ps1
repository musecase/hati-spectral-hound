$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CredentialPath = Join-Path $ProjectRoot "config\telegram-credential.clixml"

$ChatId = Read-Host "Telegram owner chat ID"
$Token = Read-Host "Telegram bot token" -AsSecureString
if (-not $ChatId -or $Token.Length -eq 0) {
    throw "Telegram chat ID and bot token cannot be blank."
}
$Credential = [PSCredential]::new($ChatId, $Token)
$Credential | Export-Clixml -LiteralPath $CredentialPath
Write-Host "Saved a Windows-user-bound Telegram credential at:"
Write-Host $CredentialPath
Write-Host "The bot token is not stored as plaintext and the file is ignored by Git."
