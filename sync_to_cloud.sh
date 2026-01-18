#!/bin/bash
# Sync local code to Oracle Cloud and restart services

set -e

# Configuration
CLOUD_IP="92.4.74.245"
SSH_KEY="$HOME/oracle_key.pem"
REMOTE_USER="ubuntu"
REMOTE_DIR="~/OptionChainUsingUpstock"
LOCAL_DIR="/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================"
echo "🚀 SYNC TO CLOUD & RESTART SERVICES"
echo "========================================"
echo ""
echo "Cloud Server: $CLOUD_IP"
echo "Local Dir: $LOCAL_DIR"
echo "Remote Dir: $REMOTE_DIR"
echo ""

# Check SSH key exists
if [ ! -f "$SSH_KEY" ]; then
    echo "${RED}❌ SSH key not found: $SSH_KEY${NC}"
    echo "Please ensure the SSH key exists or update the path in this script"
    exit 1
fi

# Check if we can connect
echo "🔍 Testing connection to cloud server..."
if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 "$REMOTE_USER@$CLOUD_IP" "echo 'Connected'" 2>/dev/null; then
    echo "${RED}❌ Cannot connect to cloud server${NC}"
    echo "Please check:"
    echo "  1. SSH key path: $SSH_KEY"
    echo "  2. Cloud server IP: $CLOUD_IP"
    echo "  3. Network connectivity"
    exit 1
fi
echo "${GREEN}✅ Connection successful${NC}"
echo ""

# Step 1: Stop local services
echo "🛑 Step 1/5: Stopping local services..."
if [ -f /tmp/background_service_pid.txt ]; then
    kill $(cat /tmp/background_service_pid.txt) 2>/dev/null && echo "  ✅ Stopped background service" || echo "  ⚠️  Background service was not running"
    rm -f /tmp/background_service_pid.txt
fi

if [ -f /tmp/backend_pid.txt ]; then
    kill $(cat /tmp/backend_pid.txt) 2>/dev/null && echo "  ✅ Stopped FastAPI backend" || echo "  ⚠️  Backend was not running"
    rm -f /tmp/backend_pid.txt
fi

if [ -f /tmp/frontend_pid.txt ]; then
    kill $(cat /tmp/frontend_pid.txt) 2>/dev/null && echo "  ✅ Stopped Next.js frontend" || echo "  ⚠️  Frontend was not running"
    rm -f /tmp/frontend_pid.txt
fi

# Also kill any remaining processes
pkill -f "background_service.py" 2>/dev/null || true
pkill -f "python.*main.py" 2>/dev/null || true
pkill -f "npm.*dev" 2>/dev/null || true

echo "${GREEN}✅ Local services stopped${NC}"
echo ""

# Step 2: Sync code (excluding sensitive files)
echo "📤 Step 2/5: Syncing code to cloud (excluding secrets, logs, cache)..."
cd "$LOCAL_DIR"

rsync -avz --progress \
    -e "ssh -i $SSH_KEY" \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.log' \
    --exclude='.streamlit/secrets.toml' \
    --exclude='venv' \
    --exclude='env' \
    --exclude='.venv' \
    --exclude='node_modules' \
    --exclude='.next' \
    --exclude='data/' \
    --exclude='logs/' \
    --exclude='snapshots/' \
    --exclude='*.pid' \
    --exclude='.DS_Store' \
    ./ "$REMOTE_USER@$CLOUD_IP:$REMOTE_DIR/"

echo "${GREEN}✅ Code synced${NC}"
echo ""

# Step 3: Copy secrets.toml separately (with updated token)
echo "🔐 Step 3/5: Updating secrets.toml on cloud..."
scp -i "$SSH_KEY" "$LOCAL_DIR/.streamlit/secrets.toml" "$REMOTE_USER@$CLOUD_IP:$REMOTE_DIR/.streamlit/secrets.toml"
echo "${GREEN}✅ Secrets updated${NC}"
echo ""

# Step 4: Restart cloud services
echo "🔄 Step 4/5: Restarting cloud services..."
ssh -i "$SSH_KEY" "$REMOTE_USER@$CLOUD_IP" << 'REMOTE_EOF'
cd ~/OptionChainUsingUpstock

echo "  Stopping services..."
sudo systemctl stop option-worker.service 2>/dev/null || true
sudo systemctl stop fastapi-backend.service 2>/dev/null || true
sudo systemctl stop nextjs-frontend.service 2>/dev/null || true
sudo systemctl stop option-dashboard.service 2>/dev/null || true

sleep 2

echo "  Starting services..."
sudo systemctl start option-worker.service
sudo systemctl start fastapi-backend.service
sudo systemctl start nextjs-frontend.service
sudo systemctl start option-dashboard.service

sleep 3

echo "  Checking service status..."
echo ""
echo "  Background Worker:"
sudo systemctl status option-worker.service --no-pager | head -3 || true
echo ""
echo "  FastAPI Backend:"
sudo systemctl status fastapi-backend.service --no-pager | head -3 || true
echo ""
echo "  Next.js Frontend:"
sudo systemctl status nextjs-frontend.service --no-pager | head -3 || true
echo ""
echo "  Streamlit Dashboard:"
sudo systemctl status option-dashboard.service --no-pager | head -3 || true
REMOTE_EOF

echo "${GREEN}✅ Cloud services restarted${NC}"
echo ""

# Step 5: Verify services
echo "🔍 Step 5/5: Verifying services..."
ssh -i "$SSH_KEY" "$REMOTE_USER@$CLOUD_IP" << 'REMOTE_EOF'
echo "  Checking if services are running..."
sleep 2

if systemctl is-active --quiet option-worker.service; then
    echo "  ✅ Background worker: RUNNING"
else
    echo "  ❌ Background worker: NOT RUNNING"
fi

if systemctl is-active --quiet fastapi-backend.service; then
    echo "  ✅ FastAPI backend: RUNNING"
else
    echo "  ❌ FastAPI backend: NOT RUNNING"
fi

if systemctl is-active --quiet nextjs-frontend.service; then
    echo "  ✅ Next.js frontend: RUNNING"
else
    echo "  ❌ Next.js frontend: NOT RUNNING"
fi

if systemctl is-active --quiet option-dashboard.service; then
    echo "  ✅ Streamlit dashboard: RUNNING"
else
    echo "  ❌ Streamlit dashboard: NOT RUNNING"
fi

echo ""
echo "  Recent logs from background worker:"
sudo journalctl -u option-worker.service -n 10 --no-pager | tail -5 || true
REMOTE_EOF

echo ""
echo "========================================"
echo "${GREEN}✅ SYNC COMPLETE!${NC}"
echo "========================================"
echo ""
echo "🌐 Access your services:"
echo "  Modern UI:     http://$CLOUD_IP/"
echo "  Streamlit:     http://$CLOUD_IP/option-chain"
echo ""
echo "📋 To check logs:"
echo "  ssh -i $SSH_KEY $REMOTE_USER@$CLOUD_IP"
echo "  sudo journalctl -u option-worker.service -f"
echo ""
