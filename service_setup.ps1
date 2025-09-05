param(
    [string]$ServiceName = "MikroTik Credential Manager",
    [string]$NssmExe = $null,
    [string]$Port = "8080",
    [string]$BindHost = "0.0.0.0",
    [string]$Debug = "False"
)

# Paths
$RepoPath   = "C:\Users\Akshay\Desktop\Mikro\Mikro Cred Manager"
$PythonPath = Join-Path $RepoPath ".venv\Scripts\python.exe"
$AppPath    = Join-Path $RepoPath "run.py"
$LogsPath   = Join-Path $RepoPath "logs"

function Fail($msg) {
    Write-Error $msg
    exit 1
}

# Check Python
if (-not (Test-Path $PythonPath)) {
    Fail "Python not found at '$PythonPath'. Ensure the virtual environment exists and dependencies are installed."
}

# Check app entrypoint
if (-not (Test-Path $AppPath)) {
    Fail "Application entry point not found at '$AppPath'."
}

# Resolve NSSM path
if (-not $NssmExe) {
    $cmd = Get-Command nssm -ErrorAction SilentlyContinue
    if ($cmd) {
        $NssmExe = $cmd.Source
    } else {
        $candidatePaths = @(
            "C:\\nssm\\nssm-2.24\\win64\\nssm.exe",
            "C:\\nssm\\nssm-2.24\\win32\\nssm.exe",
            "C:\\Program Files\\nssm\\win64\\nssm.exe",
            "C:\\Program Files (x86)\\nssm\\win64\\nssm.exe",
            "C:\\Program Files\\nssm\\win32\\nssm.exe",
            "C:\\Program Files (x86)\\nssm\\win32\\nssm.exe"
        )
        foreach ($p in $candidatePaths) {
            if (Test-Path $p) { $NssmExe = $p; break }
        }
    }
}

if (-not $NssmExe -or -not (Test-Path $NssmExe)) {
    Fail "NSSM not found. Install NSSM and rerun this script, or pass -NssmExe 'C:\\path\\to\\nssm.exe'. Download: https://nssm.cc/download"
}

Write-Host "Using NSSM at: $NssmExe"

# Ensure logs directory exists
New-Item -ItemType Directory -Path $LogsPath -Force | Out-Null

# Create or update the service
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "Service '$ServiceName' exists. Stopping it to update settings..."
    & $NssmExe stop $ServiceName | Out-Null
} else {
    Write-Host "Creating service '$ServiceName'..."
    & $NssmExe install $ServiceName $PythonPath $AppPath | Out-Null
}

# Configure service settings
& $NssmExe set $ServiceName AppDirectory $RepoPath | Out-Null

# Environment
& $NssmExe set $ServiceName AppEnvironmentExtra `
    "HOST=$BindHost" `
    "PORT=$Port" `
    "DEBUG=$Debug" `
    "DB_PATH=mikrotik_cred_manager.db" `
    "SECRET_KEY=change-me-in-production" `
    "ALGORITHM=HS256" `
    "ACCESS_TOKEN_EXPIRE_MINUTES=30" `
    "ADMIN_DEFAULT_PASSWORD=admin123" | Out-Null

# Logging
& $NssmExe set $ServiceName AppStdout (Join-Path $LogsPath "service.out.log") | Out-Null
& $NssmExe set $ServiceName AppStderr (Join-Path $LogsPath "service.err.log") | Out-Null
& $NssmExe set $ServiceName AppRotateFiles 1 | Out-Null
& $NssmExe set $ServiceName AppRotateBytes 10485760 | Out-Null
& $NssmExe set $ServiceName AppRotateOnline 1 | Out-Null

# Auto start
& $NssmExe set $ServiceName Start SERVICE_AUTO_START | Out-Null

# Firewall rule for the chosen port
$fwRuleName = "MikroTik Cred Manager HTTP $Port"
if (-not (Get-NetFirewallRule -DisplayName $fwRuleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $fwRuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port | Out-Null
}

# Start service
Write-Host "Starting service '$ServiceName'..."
& $NssmExe start $ServiceName | Out-Null

Start-Sleep -Seconds 2

# Show status
Write-Host "Service status:"
try {
    sc.exe query "$ServiceName"
    Get-Service -Name "$ServiceName" | Format-List Name,Status,StartType
} catch {
    Write-Warning "Unable to query service state. Ensure you ran this in an elevated PowerShell."
}

Write-Host "Setup complete. The app should be available at http://localhost:$Port/ (or http://<server-ip>:$Port/)"