#!/bin/bash
# Restart all services with force flag for background service

echo "🔄 Restarting all services..."

# Stop all services
echo "Stopping services..."
pkill -f background_service.py 2>/dev/null
pkill -f streamlit 2>/dev/null
pkill -f uvicorn 2>/dev/null
pkill -f next-server 2>/dev/null
sleep 3

# Start background service with --force flag
echo "Starting background service with --force flag..."
cd ~/OptionChainUsingUpstock
source venv/bin/activate
nohup python background_service.py --force > /tmp/background_force.log 2>&1 &
echo "Background service PID: $!"

# Start FastAPI backend
echo "Starting FastAPI backend..."
cd ~/OptionChainUsingUpstock/fastapi-nextjs/backend
nohup python main.py > /tmp/fastapi.log 2>&1 &
echo "FastAPI PID: $!"

# Start Next.js frontend
echo "Starting Next.js frontend..."
cd ~/OptionChainUsingUpstock/fastapi-nextjs/frontend
nohup npm start > /tmp/nextjs.log 2>&1 &
echo "Next.js PID: $!"

sleep 5

echo ""
echo "✅ Services restarted!"
echo ""
echo "Check status:"
ps aux | grep -E '[b]ackground_service|[u]vicorn|[n]ext-server' | head -3
echo ""
echo "Check logs:"
echo "  Background: tail -f /tmp/background_force.log"
echo "  FastAPI: tail -f /tmp/fastapi.log"
echo "  Next.js: tail -f /tmp/nextjs.log"
