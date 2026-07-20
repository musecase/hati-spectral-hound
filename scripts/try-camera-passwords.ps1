$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $ProjectRoot "config\hati.local.json"
$CredentialPath = Join-Path $ProjectRoot "config\camera-credential.clixml"
$Config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
$Username = "admin"
$MaximumAttempts = 10
$ExitCode = 1

Write-Host "Camera password recovery for local user: admin"
Write-Host "Try up to $MaximumAttempts candidates. Passwords remain hidden and are never logged."
Write-Host "Cancel the credential prompt to stop."
Write-Host ""

for ($Attempt = 1; $Attempt -le $MaximumAttempts; $Attempt++) {
    $Candidate = Get-Credential `
        -UserName $Username `
        -Message "Camera password candidate $Attempt of $MaximumAttempts"
    if (-not $Candidate) {
        Write-Host "Cancelled."
        break
    }

    $Password = $Candidate.GetNetworkCredential().Password
    $EncodedUsername = [Uri]::EscapeDataString($Username)
    $EncodedPassword = [Uri]::EscapeDataString($Password)
    $Url = "http://$($Config.camera.host):$($Config.camera.port)/cgi-bin/CGIProxy.fcgi" +
        "?cmd=getProductModel&usr=$EncodedUsername&pwd=$EncodedPassword"
    $Accepted = $false
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 20
        $Accepted = $Response.Content -match '<result>0</result>'
    }
    catch {
        $Accepted = $false
    }
    finally {
        $Password = $null
        $EncodedPassword = $null
        $Url = $null
    }

    if ($Accepted) {
        $Candidate | Export-Clixml -LiteralPath $CredentialPath
        Write-Host ""
        Write-Host "Password accepted. HATI's encrypted camera credential was repaired." `
            -ForegroundColor Green
        $ExitCode = 0
        break
    }

    Write-Host "Attempt $Attempt was not accepted." -ForegroundColor Yellow
    if ($Attempt -lt $MaximumAttempts) {
        Start-Sleep -Seconds 3
    }
}

if ($ExitCode -ne 0) {
    Write-Host ""
    Write-Host "No password was saved. Wait before running another set of attempts."
}
Write-Host ""
Read-Host "Press Enter to close"
exit $ExitCode
