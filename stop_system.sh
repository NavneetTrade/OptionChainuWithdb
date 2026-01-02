#!/bin/bash
# Stop both Streamlit dashboard and background service

echo "Stopping Option Chain System..."

# Stop Streamlit dashboard
if lsof -ti:8502 > /dev/null 2>&1; then
    lsof -ti:8502 | xargs kill -9 2>/dev/null
    echo "✓ Streamlit dashboard stopped"
else
    echo "✓ Streamlit dashboard not running"
fi

# Stop background service
if pgrep -f "background_service.py" > /dev/null 2>&1; then
    pkill -f "background_service.py"
    echo "✓ Background service stopped"
else
    echo "✓ Background service not running"
fi

echo "System stopped successfully"
