#!/bin/bash
# Oracle Cloud Log Checker for Option Chain System
# Server: 92.4.74.245

SERVER_IP="92.4.74.245"
SERVER_USER="${1:-ubuntu}"  # Default to ubuntu, or pass username

echo "🔍 Oracle Cloud Log Diagnostic"
echo "==============================="
echo "Server: $SERVER_IP"
echo "User: $SERVER_USER"
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Check if SSH key is available
if [ ! -f ~/.ssh/id_rsa ] && [ ! -f ~/.ssh/id_ed25519 ]; then
    echo "⚠️  No SSH key found. You may need to enter password."
fi

echo "Connecting to Oracle Cloud server..."
echo ""

# SSH command to check logs
ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'

echo "=========================================="
echo "1. SYSTEM STATUS"
echo "=========================================="
echo ""
echo "Current time (IST):"
TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S %Z'
echo ""

echo "Disk space:"
df -h / | tail -1
echo ""

echo "Memory usage:"
free -h | grep -E "Mem|Swap"
echo ""

echo "=========================================="
echo "2. BACKGROUND SERVICE STATUS"
echo "=========================================="
echo ""

# Check if running as systemd service
if systemctl list-units --type=service | grep -q "option-chain"; then
    echo "Service found in systemd:"
    sudo systemctl status option-chain-worker 2>&1 | head -20
    echo ""
elif systemctl list-units --type=service | grep -q "background"; then
    echo "Service found in systemd:"
    sudo systemctl status background-service 2>&1 | head -20
    echo ""
else
    echo "Not running as systemd service, checking processes..."
fi

echo ""
echo "Python processes running:"
ps aux | grep -E "python.*background_service|streamlit.*optionchain" | grep -v grep
echo ""

echo "=========================================="
echo "3. RECENT LOGS (Last 50 lines)"
echo "=========================================="
echo ""

# Check systemd logs if service exists
if systemctl list-units --type=service | grep -q "option-chain\|background"; then
    echo "--- Systemd Journal Logs ---"
    sudo journalctl -u option-chain-worker -n 50 --no-pager 2>/dev/null || \
    sudo journalctl -u background-service -n 50 --no-pager 2>/dev/null || \
    echo "No systemd logs found"
    echo ""
fi

# Check application log files
echo "--- Application Log Files ---"
if [ -f ~/OptionChainUsingUpstock/logs/background_service.log ]; then
    echo "Background Service Log (last 50 lines):"
    tail -50 ~/OptionChainUsingUpstock/logs/background_service.log
    echo ""
elif [ -f ~/OptionChainUsingUpstock/background_service.log ]; then
    echo "Background Service Log (last 50 lines):"
    tail -50 ~/OptionChainUsingUpstock/background_service.log
    echo ""
else
    echo "No background_service.log found"
    echo ""
fi

echo "=========================================="
echo "4. ERROR ANALYSIS"
echo "=========================================="
echo ""

# Find and analyze errors
if [ -f ~/OptionChainUsingUpstock/logs/background_service.log ]; then
    LOG_FILE=~/OptionChainUsingUpstock/logs/background_service.log
elif [ -f ~/OptionChainUsingUpstock/background_service.log ]; then
    LOG_FILE=~/OptionChainUsingUpstock/background_service.log
else
    LOG_FILE=""
fi

if [ -n "$LOG_FILE" ]; then
    echo "Errors in last 100 lines:"
    tail -100 "$LOG_FILE" | grep -i "error\|exception\|failed\|fatal" || echo "No errors found"
    echo ""
    
    echo "Token/Auth issues:"
    tail -100 "$LOG_FILE" | grep -i "token\|auth\|401\|403" || echo "No auth issues found"
    echo ""
    
    echo "Database issues:"
    tail -100 "$LOG_FILE" | grep -i "database\|postgres\|connection" || echo "No database issues found"
    echo ""
    
    echo "Last data fetch attempts:"
    tail -100 "$LOG_FILE" | grep -i "fetching\|processing\|symbol" | tail -10
    echo ""
fi

echo "=========================================="
echo "5. DATABASE STATUS"
echo "=========================================="
echo ""

if command -v psql &> /dev/null; then
    echo "Checking database connection..."
    psql -d optionchain -c "SELECT COUNT(*) as total_records, MAX(timestamp) as last_update FROM option_chain_data;" 2>&1 || echo "Database not accessible"
    echo ""
    
    echo "Recent gamma exposure updates:"
    psql -d optionchain -c "SELECT symbol, MAX(timestamp) as last_update FROM gamma_exposure_history GROUP BY symbol ORDER BY last_update DESC LIMIT 5;" 2>&1 || echo "Cannot query gamma table"
    echo ""
else
    echo "PostgreSQL client not installed"
fi

echo "=========================================="
echo "6. NETWORK & API STATUS"
echo "=========================================="
echo ""

echo "Can reach Upstox API:"
curl -s -m 5 -o /dev/null -w "HTTP Status: %{http_code}\n" https://api.upstox.com/v2/login/authorization/dialog 2>&1
echo ""

echo "=========================================="
echo "7. FILE LOCATIONS"
echo "=========================================="
echo ""

echo "Application directory:"
ls -lah ~/OptionChainUsingUpstock/ 2>/dev/null | head -10 || echo "Directory not found"
echo ""

echo "Log directory:"
ls -lah ~/OptionChainUsingUpstock/logs/ 2>/dev/null || echo "Log directory not found"
echo ""

echo "=========================================="
echo "END OF DIAGNOSTIC"
echo "=========================================="

ENDSSH

echo ""
echo "=========================================="
echo "TROUBLESHOOTING TIPS"
echo "=========================================="
echo ""
echo "If no data today (Sunday, Jan 12, 2026):"
echo "  ✓ This is normal - market is closed on weekends"
echo ""
echo "If service not running:"
echo "  ssh ${SERVER_USER}@${SERVER_IP}"
echo "  cd ~/OptionChainUsingUpstock"
echo "  ./start_system.sh"
echo ""
echo "If token expired:"
echo "  ssh ${SERVER_USER}@${SERVER_IP}"
echo "  cd ~/OptionChainUsingUpstock"
echo "  # Update token in .streamlit/secrets.toml"
echo ""
echo "To restart service:"
echo "  ssh ${SERVER_USER}@${SERVER_IP}"
echo "  sudo systemctl restart option-chain-worker"
echo ""
