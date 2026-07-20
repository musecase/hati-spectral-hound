$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CredentialPath = Join-Path $ProjectRoot "config\camera-credential.clixml"
$ConfigPath = Join-Path $ProjectRoot "config\hati.local.json"
$ExitCode = 1

Write-Host "Trying the encrypted saved camera password with the primary local username."
Write-Host "The password will not be displayed or written as plaintext."
Write-Host ""

try {
    $Config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    $Saved = Import-Clixml -LiteralPath $CredentialPath
    $Password = $Saved.GetNetworkCredential().Password
    $Username = "admin"
    $EncodedUsername = [Uri]::EscapeDataString($Username)
    $EncodedPassword = [Uri]::EscapeDataString($Password)
    $Url = "http://$($Config.camera.host):$($Config.camera.port)/cgi-bin/CGIProxy.fcgi" +
        "?cmd=getProductModel&usr=$EncodedUsername&pwd=$EncodedPassword"
    $Response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 20
    if ($Response.Content -notmatch '<result>0</result>') {
        throw "The saved password was not accepted for the admin camera account."
    }

    $Repaired = [Management.Automation.PSCredential]::new($Username, $Saved.Password)
    $Repaired | Export-Clixml -LiteralPath $CredentialPath
    Write-Host "Recovered the camera login and repaired HATI's encrypted credential." -ForegroundColor Green
    $ExitCode = 0
}
catch {
    Write-Host "Camera login recovery did not match:" -ForegroundColor Yellow
    Write-Host $_.Exception.Message
}
finally {
    $Password = $null
    $EncodedPassword = $null
    $Url = $null
    Write-Host ""
    Read-Host "Press Enter to close"
}

exit $ExitCode
