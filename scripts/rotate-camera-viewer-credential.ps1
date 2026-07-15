$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CredentialPath = Join-Path $ProjectRoot "config\camera-credential.clixml"
$ReadyPath = Join-Path $ProjectRoot "config\camera-credential-ready.marker"
$Username = "hati_viewer"

Remove-Item -LiteralPath $ReadyPath -ErrorAction SilentlyContinue

$Generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $Password = ""
    while ($Password.Length -lt 12) {
        $Bytes = New-Object byte[] 18
        $Generator.GetBytes($Bytes)
        $Password += ([Convert]::ToBase64String($Bytes) -replace '[^A-Za-z0-9]', '')
    }
    $Password = $Password.Substring(0, 12)
} finally {
    $Generator.Dispose()
}

$SecurePassword = ConvertTo-SecureString $Password -AsPlainText -Force
$Credential = [PSCredential]::new($Username, $SecurePassword)
$Credential | Export-Clixml -LiteralPath $CredentialPath
Set-Clipboard -Value $Password

Write-Host "A new 12-character HATI viewer password is on the clipboard."
Write-Host "In the open Foscam User Accounts page:"
Write-Host "  1. Select hati_viewer."
Write-Host "  2. Paste into Password and Confirm Password."
Write-Host "  3. Keep the role Operator and click Save."
Write-Host "  4. Return here and press Enter."
Read-Host "Press Enter only after the camera page reports the account was saved"

Set-Clipboard -Value ""
$Password = $null
$SecurePassword.Dispose()
New-Item -ItemType File -Force -Path $ReadyPath | Out-Null
Write-Host "Clipboard cleared. HATI can now retry the camera login."
