#!/bin/bash

# Complete System Startup Script
# Starts both TimescaleDB (if using Docker), Background Service, and Streamlit UI

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Option Chain System - Complete Startup"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Check TimescaleDB
echo "Step 1: Checking TimescaleDB..."
if docker ps | grep -q timescaledb; then
    echo -e "${GREEN}✓ TimescaleDB (Docker) is running${NC}"
elif psql -U postgres -d optionchain -c "SELECT 1;" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ TimescaleDB (Local) is running${NC}"
else
    echo -e "${YELLOW}⚠ TimescaleDB not detected${NC}"
    echo "  Options:"
    echo "  1. Start Docker: docker start timescaledb"
    echo "  2. Start local: brew services start postgresql"
    echo "  3. Continue without DB (Direct API Mode)"
    read -p "  Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo ""

# Step 2: Check database connection
echo "Step 2: Testing database connection..."
python3 -c "
from database import TimescaleDBManager
try:
    db = TimescaleDBManager()
    if db.pool:
        print('✓ Database connected successfully')
        exit(0)
    else:
        print('⚠ Database not available - will use Direct API Mode')
        exit(1)
except Exception as e:
    print(f'⚠ Database error: {str(e)[:60]}...')
    exit(1)
" 2>/dev/null

DB_STATUS=$?
if [ $DB_STATUS -eq 0 ]; then
    echo -e "${GREEN}✓ Database connection OK${NC}"
    MODE="Production Mode (Database)"
else
    echo -e "${YELLOW}⚠ Database not available - using Direct API Mode${NC}"
    MODE="Direct API Mode"
fi
echo ""

# Step 3: Check if background service is already running
echo "Step 3: Checking background service..."
if pgrep -f "background_service.py" > /dev/null; then
    echo -e "${YELLOW}⚠ Background service is already running${NC}"
    read -p "  Kill existing process and restart? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pkill -f background_service.py
        sleep 2
    else
        echo "  Keeping existing process"
        SKIP_BG=true
    fi
else
    SKIP_BG=false
fi

# Step 4: Start background service
if [ "$SKIP_BG" != "true" ]; then
    echo "Step 4: Starting background service..."
    nohup python3 background_service.py --interval 30 > background_service.log 2>&1 &
    BG_PID=$!
    sleep 3
    
    if ps -p $BG_PID > /dev/null; then
        echo -e "${GREEN}✓ Background service started (PID: $BG_PID)${NC}"
        echo "  Logs: background_service.log"
    else
        echo -e "${RED}✗ Failed to start background service${NC}"
        echo "  Check logs: tail -20 background_service.log"
        exit 1
    fi
else
    BG_PID=$(pgrep -f "background_service.py" | head -1)
    echo -e "${GREEN}✓ Using existing background service (PID: $BG_PID)${NC}"
fi
echo ""

# Step 5: Check if Streamlit is already running
echo "Step 5: Checking Streamlit UI..."
if lsof -ti:8501 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Streamlit is already running on port 8501${NC}"
    read -p "  Kill existing process and restart? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        kill $(lsof -ti:8501) 2>/dev/null
        sleep 2
    else
        echo "  Keeping existing process"
        SKIP_UI=true
    fi
else
    SKIP_UI=false
fi

# Step 6: Start Streamlit
if [ "$SKIP_UI" != "true" ]; then
    echo "Step 6: Starting Streamlit UI..."
    echo ""
    echo "=========================================="
    echo "System Status:"
    echo "  Mode: $MODE"
    echo "  Background Service: Running (PID: $BG_PID)"
    echo "  Streamlit UI: Starting..."
    echo "=========================================="
    echo ""
    echo "The UI will open at: http://localhost:8501"
    echo ""
    echo "Press Ctrl+C to stop all services"
    echo ""
    
    # Function to cleanup on exit
    cleanup() {
        echo ""
        echo "Stopping services..."
        if [ ! -z "$BG_PID" ]; then
            kill $BG_PID 2>/dev/null && echo "✓ Background service stopped"
        fi
        kill $(lsof -ti:8501) 2>/dev/null && echo "✓ Streamlit stopped"
        echo "All services stopped"
        exit 0
    }
    
    trap cleanup SIGINT SIGTERM
    
    # Start Streamlit in foreground
    streamlit run optionchain.py --server.port=8501
    
    # Cleanup if streamlit exits
    cleanup
else
    echo -e "${GREEN}✓ Streamlit UI is already running${NC}"
    echo ""
    echo "=========================================="
    echo "System Status:"
    echo "  Mode: $MODE"
    echo "  Background Service: Running (PID: $BG_PID)"
    echo "  Streamlit UI: http://localhost:8501"
    echo "=========================================="
    echo ""
    echo "To stop services:"
    echo "  pkill -f background_service.py"
    echo "  kill \$(lsof -ti:8501)"
fi

