# Fix 504 Gateway Timeout - Quick Guide

## Problem
504 Gateway Timeout - Nginx reverse proxy is timing out waiting for backend services

## Solution

### Step 1: Fix Nginx Timeout (Run on Server)

```bash
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245
cd ~
bash fix_nginx_timeout.sh
```

This will:
- Increase nginx timeouts to 300-600 seconds
- Reload nginx configuration
- Fix 504 errors

### Step 2: Restart Services Properly

```bash
# Kill all processes
pkill -f background_service.py
pkill -f uvicorn
pkill -f next-server
pkill -f streamlit
sleep 3

# Start background service with --force
cd ~/OptionChainUsingUpstock
source venv/bin/activate
nohup python background_service.py --force > /tmp/background_force.log 2>&1 &

# Start FastAPI (make sure port 8000 is free)
cd ~/OptionChainUsingUpstock/fastapi-nextjs/backend
nohup python main.py > /tmp/fastapi.log 2>&1 &

# Start Next.js
cd ~/OptionChainUsingUpstock/fastapi-nextjs/frontend
nohup npm start > /tmp/nextjs.log 2>&1 &

# Wait and check
sleep 5
ps aux | grep -E '[b]ackground_service|[u]vicorn|[n]ext-server'
```

### Step 3: Verify Services

```bash
# Check if services are responding
curl http://localhost:8000/  # FastAPI
curl http://localhost:3000/  # Next.js

# Check nginx
sudo systemctl status nginx
sudo tail -f /var/log/nginx/error.log
```

### Step 4: Check Logs for Errors

```bash
# FastAPI logs
tail -50 /tmp/fastapi.log

# Background service logs
tail -50 /tmp/background_force.log

# Next.js logs
tail -50 /tmp/nextjs.log

# Nginx error log
sudo tail -50 /var/log/nginx/error.log
```

## Alternative: Use systemd Services

If services are managed by systemd:

```bash
# Restart all services
sudo systemctl restart option-worker
sudo systemctl restart fastapi-backend
sudo systemctl restart nextjs-frontend
sudo systemctl restart nginx

# Check status
sudo systemctl status option-worker
sudo systemctl status fastapi-backend
sudo systemctl status nextjs-frontend
```

## Common Issues

1. **Port already in use:**
   ```bash
   netstat -tlnp | grep -E ':(3000|8000|8501)'
   # Kill the process using the port
   ```

2. **Database connection issues:**
   ```bash
   psql -U optionuser -d optionchain -c "SELECT 1;"
   ```

3. **Out of memory:**
   ```bash
   free -h
   # May need to restart server or reduce services
   ```

## Quick One-Liner Fix

```bash
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245 "bash ~/fix_nginx_timeout.sh && pkill -f 'uvicorn|next-server|background_service'; sleep 3; cd ~/OptionChainUsingUpstock && source venv/bin/activate && nohup python background_service.py --force > /tmp/bg.log 2>&1 & cd fastapi-nextjs/backend && nohup python main.py > /tmp/api.log 2>&1 & cd ../frontend && nohup npm start > /tmp/next.log 2>&1 &"
```
