#!/bin/bash

# Stop all services: Background Service and UI
# Usage: ./stop_all.sh

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          Stopping Option Chain System Services              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Stop background service
if pgrep -f "background_service.py" > /dev/null; then
    echo "Stopping background service..."
    pkill -f background_service.py
    sleep 1
    echo "✓ Background service stopped"
else
    echo "⚠ Background service not running"
fi

# Stop Streamlit UI
if lsof -ti:8501 > /dev/null 2>&1; then
    echo "Stopping Streamlit UI..."
    kill $(lsof -ti:8501) 2>/dev/null
    sleep 1
    echo "✓ Streamlit UI stopped"
else
    echo "⚠ Streamlit UI not running"
fi

echo ""
echo "✅ All services stopped"
echo ""
echo "Note: PostgreSQL/TimescaleDB is still running (managed by Homebrew)"
echo "To stop database: brew services stop postgresql@17"

