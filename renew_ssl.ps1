param(
    [string]$Domain = "syslog.techguru.net",
    [string]$WacsExe = "C:\letsencrypt\wacs\wacs.exe",
    [string]$CertOutDir = "C:\letsencrypt\certs\syslog.techguru.net",
    [string]$EnvFile = "c:\Users\Akshay\Desktop\Mikro\Mikro Cred Manager\.env"
)

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

if (-not (Test-Path $WacsExe)) { Write-Err "wacs.exe not found at $WacsExe"; exit 1 }

# Renew all due certificates using win-acme defaults
& $WacsExe --renew --baseuri https://acme-v02.api.letsencrypt.org/ --verbose
if ($LASTEXITCODE -ne 0) { Write-Err "win-acme renew failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }

# Validate files still exist
$certFile = Join-Path $CertOutDir 'fullchain.pem'
$keyFile  = Join-Path $CertOutDir 'privkey.pem'
if (-not (Test-Path $certFile) -or -not (Test-Path $keyFile)) {
    Write-Err "Expected renewed files not found: $certFile / $keyFile"
    exit 1
}

# Restart app to reload certs
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

Write-Host "Renewal complete for $Domain. Certificates reloaded." -ForegroundColor Green