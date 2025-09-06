# MikroTik Credential Manager (Windows, SQLite)

A secure web-based platform to create and auto-clean temporary credentials on MikroTik devices. This guide focuses on a clean Windows deployment with SQLite, public access, and optional HTTPS via Let's Encrypt (win-acme).

---

## Features
- **Temporary credentials**: Time-bound MikroTik users with auto-cleanup
- **Roles**: Admin, Full, Write, Read-only
- **Audit logs**: Session/activity logging in SQLite
- **Simple setup**: No external DB required (SQLite)
- **HTTPS-ready**: win-acme (Let’s Encrypt) automation for TLS

---

## Requirements
- Windows 10/11 or Windows Server 2019+
- Python 3.11+ installed and in PATH
- PowerShell (Run as Administrator for firewall/SSL/service steps)
- MikroTik RouterOS devices reachable on API port (8728 or 8729)

Optional for HTTPS and service:
- win-acme (wacs.exe) for Let’s Encrypt on Windows
- NSSM (Non-Sucking Service Manager) for running as a Windows service

---

## 1) Download and install

1. Open PowerShell and navigate to a folder where you want the app.
2. Clone the repository:
   ```powershell
   git clone https://github.com/aksha-y/working_Mikro_Cred_Manager.git
   Set-Location .\working_Mikro_Cred_Manager
   ```
3. Create a virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

---

## 2) Configure environment (.env)

1. Create your .env from template:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Edit `.env` and set at minimum:
   - **SECRET_KEY**: long random string
   - **HOST**: `0.0.0.0` (to listen on all interfaces)
   - **PORT**: e.g. `8080`
   - **MIKROTIK_SERVICE_USER / MIKROTIK_SERVICE_PASSWORD**: service account present on each RouterOS device
   - **MIKROTIK_API_PORT**: 8728 for plain API (default) or 8729 for TLS
   - **MIKROTIK_API_TLS**: `false` for 8728, `true` for 8729

Demo of .example .enc file data
   ```
# MikroTik Credential Manager Configuration

# Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=mikrotik_cred_manager

# Application Configuration
SECRET_KEY=your-super-secret-key-change-this-in-production-12345
HOST=localhost
PORT=8000
DEBUG=True

# MikroTik Configuration
MIKROTIK_SERVICE_USER=service_user
MIKROTIK_SERVICE_PASSWORD=service_password
MIKROTIK_API_PORT=20829
ADMIN_DEFAULT_PASSWORD=admin123

# Security Settings
SESSION_EXPIRE_MINUTES=480
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=15

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=app.log
LOG_MAX_SIZE=10485760
LOG_BACKUP_COUNT=5

# System Settings
TIMEZONE=UTC
DEFAULT_TEMP_USER_PREFIX=temp_
MAX_CONCURRENT_SESSIONS=10
SESSION_CLEANUP_INTERVAL=300
LOG_RETENTION_DAYS=90

# Feature Flags
ENABLE_EMAIL_NOTIFICATIONS=False
ENABLE_API_RATE_LIMITING=True
ENABLE_AUDIT_LOGGING=True
ENABLE_AUTO_CLEANUP=True
```

Note: Do not commit `.env` to GitHub.

---

## 3) Initialize database

SQLite is auto-initialized on first start. If you prefer, you can run the helper once:
```powershell
.\.venv\Scripts\python.exe .\init_db_sqlite.py
```
This creates tables and a default admin (password from `.env` ADMIN_DEFAULT_PASSWORD, default `admin123`).

---

## 4) Start the application

```powershell
.\.venv\Scripts\python.exe .\run.py
```
- App reads `.env` and starts Uvicorn
- Access locally: `http://localhost:8080`
- Default login: `admin / admin123` (change after first login)

---
- if still not working the please remove the file from the folder mikrotik_cred_manager.db and re run this command : .\.venv\Scripts\python.exe .\run.py

## 5) Open Windows Firewall (for public access)

Run as Administrator:
```powershell
powershell -ExecutionPolicy Bypass -File .\setup_firewall.ps1
```
- Ensure your cloud provider/network security group also allows inbound TCP 8080.
- Access externally: `http://YOUR_PUBLIC_IP:8080`

If you use a different port, update `.env` PORT and open that port instead.

---

## 6) Configure MikroTik devices

On each router, create a service account with API permissions that matches your `.env`:
```routeros
/user group add name=api_service policy=api,read,write,policy,test
/user add name=service_user password=strong_service_password group=api_service
/ip service enable api
/ip service set api port=8728   # for plain API
# For TLS/SSL API, use port 8729 and set MIKROTIK_API_TLS=true in .env
```

---

## 7) Enable HTTPS (Let's Encrypt with win-acme)

Prerequisites:
- A domain name pointing (A/AAAA record) to your server’s public IP
- Port 80 open on the server and reachable publicly (for HTTP-01 validation)

Steps:
1. Download win-acme (wacs.exe) from https://github.com/win-acme/win-acme/releases (x64 trimmed zip works).
2. Extract to `C:\letsencrypt\wacs\wacs.exe` (or adjust path below).
3. Run the helper script as Administrator, replacing values:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup_ssl.ps1 -Domain "yourdomain.com" -Email "admin@yourdomain.com"
   ```
   - This obtains certs, writes them to `C:\letsencrypt\certs\yourdomain.com`, updates `.env` with `SSL_CERTFILE`, `SSL_KEYFILE`, sets `SECURE_COOKIES=true`.
4. Restart the app and browse: `https://yourdomain.com/`.

Renewal:
```powershell
powershell -ExecutionPolicy Bypass -File .\renew_ssl.ps1 -Domain "yourdomain.com"
```

---

## 8) Run as Windows Service (Optional)

Install NSSM (https://nssm.cc/download) and then run as Administrator:
```powershell
powershell -ExecutionPolicy Bypass -File .\service_setup.ps1 -Port 8080 -BindHost 0.0.0.0
```
- The script creates a service using the venv’s python and `run.py`
- Logs are rotated to `./logs/service.*.log`

---

## Security best practices
- Change the default admin password immediately
- Use a strong `SECRET_KEY` and keep `.env` private
- Prefer HTTPS in production (`SECURE_COOKIES=true`)
- Restrict inbound ports at your cloud firewall
- Use service accounts with minimum RouterOS policies

---

## What’s included (deployment files)
- Application: `main.py`, `run.py`, `database.py`, `auth.py`, `mikrotik_api.py`, `mikrotik_manager.py`
- UI: `templates/`, `static/`
- Config: `.env.example`, `requirements.txt`, `.gitignore`
- Windows ops: `setup_firewall.ps1`, `setup_ssl.ps1`, `renew_ssl.ps1`, `service_setup.ps1`

Excluded from Git: `.env`, local DB files (`*.db`), logs, venv, and other unneeded artifacts.

---

## Troubleshooting
- Port busy: change `PORT` in `.env` and re-open firewall for that port
- Cannot reach router: check `MIKROTIK_API_PORT`, device firewall, and service user rights
- HTTPS fails: ensure DNS points to server public IP, port 80 reachable, rerun `setup_ssl.ps1`

---

## License
See `LICENSE`.
