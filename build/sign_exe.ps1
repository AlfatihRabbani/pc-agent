# Self-sign PC-Agent.exe so Windows stops treating it as an "unknown publisher".
#
# A self-signed cert only removes the warning on machines that TRUST the cert
# (this one, once you import it below). For distributing to OTHER people without
# SmartScreen warnings you need a real code-signing certificate from a CA.
#
# Run in an ADMIN PowerShell:  powershell -ExecutionPolicy Bypass -File build\sign_exe.ps1

$exe = Join-Path $PSScriptRoot "..\PC-Agent.exe"
if (-not (Test-Path $exe)) { Write-Host "PC-Agent.exe not found — build it first."; exit 1 }

$subject = "CN=AlfatihRabbani PC-Agent"
$cert = Get-ChildItem Cert:\CurrentUser\My |
        Where-Object { $_.Subject -eq $subject } | Select-Object -First 1
if (-not $cert) {
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $subject `
        -CertStoreLocation Cert:\CurrentUser\My -KeyUsage DigitalSignature `
        -FriendlyName "AlfatihRabbani PC-Agent code signing" -NotAfter (Get-Date).AddYears(5)
    Write-Host "Created self-signed code-signing certificate."
}

Set-AuthenticodeSignature -FilePath $exe -Certificate $cert -HashAlgorithm SHA256 |
    Format-List Status, StatusMessage

# Trust it on THIS machine (removes the 'unknown publisher' prompt). Needs admin.
try {
    $tmp = Join-Path $env:TEMP "pc-agent-codesign.cer"
    Export-Certificate -Cert $cert -FilePath $tmp | Out-Null
    Import-Certificate -FilePath $tmp -CertStoreLocation Cert:\LocalMachine\Root          | Out-Null
    Import-Certificate -FilePath $tmp -CertStoreLocation Cert:\LocalMachine\TrustedPublisher | Out-Null
    Remove-Item $tmp -ErrorAction SilentlyContinue
    Write-Host "Certificate trusted on this PC (Root + TrustedPublisher)."
} catch {
    Write-Host "Could not install cert to trusted stores (run as admin to do that): $_"
}
