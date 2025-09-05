# PowerShell script to setup firewall rule for MikroTik Credential Manager
# Run this as Administrator

Write-Host "Setting up Windows Firewall rule for MikroTik Credential Manager..." -ForegroundColor Green

try {
    # Add firewall rule for port 8080
    New-NetFirewallRule -DisplayName "MikroTik Credential Manager" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Any
    Write-Host "✅ Firewall rule added successfully!" -ForegroundColor Green
    Write-Host "Port 8080 is now open for incoming connections" -ForegroundColor Yellow
} catch {
    Write-Host "❌ Failed to add firewall rule: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Please run this script as Administrator" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🌐 Your MikroTik Credential Manager is now accessible at:" -ForegroundColor Cyan
Write-Host "   Local: http://localhost:8080" -ForegroundColor White
Write-Host "   Network: http://YOUR_SERVER_IP:8080" -ForegroundColor White
Write-Host ""
Write-Host "🔑 Default login credentials:" -ForegroundColor Cyan
Write-Host "   Username: admin" -ForegroundColor White
Write-Host "   Password: admin123" -ForegroundColor White
Write-Host ""
Write-Host "⚠️  Please change the default password after first login!" -ForegroundColor Yellow

Read-Host "Press Enter to continue..."