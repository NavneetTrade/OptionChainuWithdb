#!/bin/bash

# Script to start both background service and Streamlit app

echo "=========================================="
echo "Starting Option Chain System"
echo "=========================================="

# Check if TimescaleDB is running
echo ""
echo "Checking database connection..."
python3 -c "from database import TimescaleDBManager; db = TimescaleDBManager(); print('✓ Database connected')" 2>&1 | grep -q "connected" && DB_OK=true || DB_OK=false

if [ "$DB_OK" = false ]; then
    echo "⚠ Database not available - service will run without DB storage"
    echo "  (This is OK for testing, but data won't be persisted)"
else
    echo "✓ Database connection OK"
fi

# Start background service in background
echo ""
echo "Starting background service..."
cd "$(dirname "$0")"
nohup python3 background_service.py --interval 30 > background_service.log 2>&1 &
BG_PID=$!
echo "✓ Background service started (PID: $BG_PID)"
echo "  Logs: background_service.log"

# Wait a moment for service to initialize
sleep 2

# Start Streamlit app
echo ""
echo "Starting Streamlit dashboard..."
echo "  URL: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop all services"
echo "=========================================="

# Start Streamlit in foreground so user can see output
streamlit run optionchain.py --server.port=8501

# Cleanup on exit
echo ""
echo "Stopping background service (PID: $BG_PID)..."
kill $BG_PID 2>/dev/null
echo "✓ Services stopped"

