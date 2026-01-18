# Quick Restart Guide - Fix 504 Gateway Timeout

## Problem
504 Gateway Timeout - Services may be overloaded or not responding

## Quick Fix - Run on Server

SSH to your server and run:

```bash
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245

# Then run:
cd ~
bash restart_services.sh
```

## Or Run Commands Manually

```bash
# 1. Stop all services
pkill -f background_service.py
pkill -f streamlit  
pkill -f uvicorn
pkill -f next-server
sleep 3

# 2. Start background service with --force
cd ~/OptionChainUsingUpstock
source venv/bin/activate
nohup python background_service.py --force > /tmp/background_force.log 2>&1 &

# 3. Start FastAPI
cd ~/OptionChainUsingUpstock/fastapi-nextjs/backend
nohup python main.py > /tmp/fastapi.log 2>&1 &

# 4. Start Next.js
cd ~/OptionChainUsingUpstock/fastapi-nextjs/frontend
nohup npm start > /tmp/nextjs.log 2>&1 &

# 5. Check status
ps aux | grep -E '[b]ackground_service|[u]vicorn|[n]ext-server'
```

## Verify Services

```bash
# Check if services are running
curl http://localhost:8000/  # FastAPI
curl http://localhost:3000/  # Next.js

# Check logs for errors
tail -50 /tmp/fastapi.log
tail -50 /tmp/background_force.log
```

## If Still Getting 504

1. **Check server resources:**
   ```bash
   free -h
   df -h
   top
   ```

2. **Check if ports are in use:**
   ```bash
   netstat -tlnp | grep -E ':(3000|8000|8501)'
   ```

3. **Restart with more memory:**
   - May need to increase server resources
   - Or reduce number of symbols being processed

4. **Check database connection:**
   ```bash
   psql -U optionuser -d optionchain -c "SELECT 1;"
   ```
