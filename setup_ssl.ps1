param(
    [string]$Domain = "syslog.techguru.net",
    [string]$WacsExe = "C:\letsencrypt\wacs\wacs.exe",
    [string]$CertOutDir = "C:\letsencrypt\certs\syslog.techguru.net",
    [string]$EnvFile = "c:\Users\Akshay\Desktop\Mikro\Mikro Cred Manager\.env",
    [int]$HttpsPort = 443,
    [string]$Email = "admin@syslog.techguru.net"
)

# Utility: Write info
function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

Write-Info "Domain: $Domain"
Write-Info "wacs.exe path: $WacsExe"
Write-Info "Output cert dir: $CertOutDir"

# Ensure directories
$wacsDir = Split-Path $WacsExe -Parent
if (-not (Test-Path $wacsDir)) { New-Item -ItemType Directory -Path $wacsDir -Force | Out-Null }
if (-not (Test-Path $CertOutDir)) { New-Item -ItemType Directory -Path $CertOutDir -Force | Out-Null }

# Check wacs.exe
if (-not (Test-Path $WacsExe)) {
    Write-Warn "wacs.exe not found at $WacsExe."
    Write-Warn "Please download win-acme (wacs.exe) and place it at the specified path."
    Write-Warn "Download: https://github.com/win-acme/win-acme/releases (x64 trimmed zip is fine)"
    Write-Warn "Then rerun this script."
    exit 1
}

# Check port 80 availability (for HTTP-01 validation)
try {
    $inUse = (Get-NetTCPConnection -LocalPort 80 -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0
} catch { $inUse = $false }
if ($inUse) {
    Write-Warn "Port 80 appears to be in use. win-acme self-host validation needs to bind to port 80."
    Write-Warn "Stop any service using port 80 temporarily (IIS/Apache/Nginx) before continuing."
}

# Ensure firewall for 80/443
try { New-NetFirewallRule -DisplayName "MikroTik Cred Manager HTTP (80)" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow -Profile Any -ErrorAction SilentlyContinue | Out-Null } catch {}
try { New-NetFirewallRule -DisplayName "MikroTik Cred Manager HTTPS (443)" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -Profile Any -ErrorAction SilentlyContinue | Out-Null } catch {}

Write-Info "Requesting Let's Encrypt certificate via HTTP-01 (self-host)"
# Run win-acme in unattended mode to issue PEM files
& $WacsExe --target manual `
          --host $Domain `
          --validationport 80 `
          --validationmode selfhosting `
          --emailaddress $Email `
          --accepttos `
          --store pemfiles `
          --pemfilespath $CertOutDir `
          --friendlyname "$Domain-uvicorn" `
          --closeonfinish  
if ($LASTEXITCODE -ne 0) {
    Write-Err "win-acme failed (exit $LASTEXITCODE). Check output above."
    exit $LASTEXITCODE
}

# Expecting files like: fullchain.pem, chain.pem, cert.pem, privkey.pem
# Map win-acme PEM names to uvicorn expected names
$certFile = Join-Path $CertOutDir ("{0}-chain.pem" -f $Domain)
$keyFile  = Join-Path $CertOutDir ("{0}-key.pem" -f $Domain)

if (-not (Test-Path $certFile) -or -not (Test-Path $keyFile)) {
    # Fallback to generic names if plugin changes
    $genericCert = Join-Path $CertOutDir 'fullchain.pem'
    $genericKey  = Join-Path $CertOutDir 'privkey.pem'
    if ((Test-Path $genericCert) -and (Test-Path $genericKey)) {
        $certFile = $genericCert
        $keyFile  = $genericKey
    } else {
        Write-Err "Certificate files not found in $CertOutDir. Looked for $Domain-chain.pem/$Domain-key.pem or fullchain.pem/privkey.pem."
        exit 1
    }
}
Write-Info "Certificate generated: $certFile"
Write-Info "Private key: $keyFile"

# Update .env for uvicorn SSL
if (-not (Test-Path $EnvFile)) {
    Write-Warn ".env not found at $EnvFile. Skipping env update."
} else {
    Write-Info "Updating .env with SSL paths and enabling secure cookies"
    $envText = Get-Content -Path $EnvFile -Raw

    # Helper to upsert a key=value in .env
    function Set-EnvLine([string]$text, [string]$key, [string]$value) {
        $pattern = "(?m)^(" + [regex]::Escape($key) + ")=.*$"
        if ($text -match $pattern) {
            return ([regex]::Replace($text, $pattern, "$key=$value"))
        } else {
            if (-not $text.EndsWith("`n")) { $text += "`n" }
            return $text + "$key=$value`n"
        }
    }

    $envText = Set-EnvLine $envText 'SSL_CERTFILE' $certFile
    $envText = Set-EnvLine $envText 'SSL_KEYFILE' $keyFile
    $envText = Set-EnvLine $envText 'HTTPS_PORT' $HttpsPort
    $envText = Set-EnvLine $envText 'SECURE_COOKIES' 'true'

    Set-Content -Path $EnvFile -Value $envText -Encoding UTF8
    Write-Info ".env updated."
}

# Try to restart app (service or scheduled task)
function Restart-App {
    $serviceName = 'MikroCredManager'
    $taskName = 'MikroTikCredManager'

    $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Info "Restarting service '$serviceName'"
        if ($svc.Status -eq 'Running') { Restart-Service -Name $serviceName -Force }
        else { Start-Service -Name $serviceName }
        return
    }

    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        Write-Info "Restarting scheduled task '$taskName'"
        try { Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue } catch {}
        Start-ScheduledTask -TaskName $taskName
        return
    }

    Write-Warn "No known service or scheduled task found to restart. Restart the app manually."
}

Restart-App

Write-Host ("`nDone. Access via: https://{0}/ (if DNS points here and 443 open) or https://{0}:{1}/" -f $Domain, $HttpsPort) -ForegroundColor Green