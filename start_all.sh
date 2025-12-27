#!/bin/bash

# Single command to start everything: Database, Background Service, and UI
# Usage: ./start_all.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Starting Complete Option Chain System                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Check and start PostgreSQL/TimescaleDB
echo "Step 1: Checking PostgreSQL/TimescaleDB..."
if brew services list | grep -q "postgresql@17.*started"; then
    echo -e "${GREEN}✓ PostgreSQL 17 is running${NC}"
elif brew services list | grep -q "postgresql@14.*started"; then
    echo -e "${GREEN}✓ PostgreSQL 14 is running${NC}"
else
    echo -e "${YELLOW}⚠ Starting PostgreSQL...${NC}"
    if brew services list | grep -q "postgresql@17"; then
        brew services start postgresql@17
    elif brew services list | grep -q "postgresql@14"; then
        brew services start postgresql@14
    else
        echo -e "${RED}✗ PostgreSQL not found. Please install it first.${NC}"
        exit 1
    fi
    sleep 3
    echo -e "${GREEN}✓ PostgreSQL started${NC}"
fi
echo ""

# Step 2: Set environment variables and verify database connection
echo "Step 2: Setting environment variables and verifying database connection..."
export DB_HOST=${DB_HOST:-localhost}
export DB_PORT=${DB_PORT:-5432}
export DB_NAME=${DB_NAME:-optionchain}
export DB_USER=${DB_USER:-$(whoami)}
export DB_PASSWORD=${DB_PASSWORD:-}

python3 -c "
import os
from database import TimescaleDBManager
try:
    # Ensure environment variables are set
    os.environ.setdefault('DB_HOST', 'localhost')
    os.environ.setdefault('DB_PORT', '5432')
    os.environ.setdefault('DB_NAME', 'optionchain')
    os.environ.setdefault('DB_USER', '$(whoami)')
    
    db = TimescaleDBManager()
    if db.pool:
        print('✓ Database connected')
        exit(0)
    else:
        print('✗ Database connection failed')
        exit(1)
except Exception as e:
    print(f'✗ Error: {str(e)[:60]}...')
    exit(1)
" 2>/dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Database connection verified${NC}"
else
    echo -e "${YELLOW}⚠ Database connection issue (will continue anyway)${NC}"
fi
echo ""

# Step 3: Stop existing services if running
echo "Step 3: Cleaning up existing services..."
if pgrep -f "background_service.py" > /dev/null; then
    echo "  Stopping existing background service..."
    pkill -f background_service.py
    sleep 1
fi

if lsof -ti:8501 > /dev/null 2>&1; then
    echo "  Stopping existing Streamlit UI..."
    kill $(lsof -ti:8501) 2>/dev/null
    sleep 1
fi
echo -e "${GREEN}✓ Cleanup complete${NC}"
echo ""

# Step 4: Start background service
echo "Step 4: Starting background service..."
# Ensure environment variables are exported for the background process
export DB_HOST=${DB_HOST:-localhost}
export DB_PORT=${DB_PORT:-5432}
export DB_NAME=${DB_NAME:-optionchain}
export DB_USER=${DB_USER:-$(whoami)}
export DB_PASSWORD=${DB_PASSWORD:-}

nohup env DB_HOST=$DB_HOST DB_PORT=$DB_PORT DB_NAME=$DB_NAME DB_USER=$DB_USER python3 background_service.py --interval 30 > background_service.log 2>&1 &
BG_PID=$!
sleep 3

if ps -p $BG_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Background service started (PID: $BG_PID)${NC}"
    echo "  Logs: background_service.log"
else
    echo -e "${RED}✗ Failed to start background service${NC}"
    echo "  Check logs: tail -20 background_service.log"
    exit 1
fi
echo ""

# Step 5: Start Streamlit UI
echo "Step 5: Starting Streamlit UI..."
# Ensure environment variables are exported for Streamlit
export DB_HOST=${DB_HOST:-localhost}
export DB_PORT=${DB_PORT:-5432}
export DB_NAME=${DB_NAME:-optionchain}
export DB_USER=${DB_USER:-$(whoami)}
export DB_PASSWORD=${DB_PASSWORD:-}

nohup env DB_HOST=$DB_HOST DB_PORT=$DB_PORT DB_NAME=$DB_NAME DB_USER=$DB_USER python3 -m streamlit run optionchain.py --server.port=8501 --server.headless=true > streamlit.log 2>&1 &
ST_PID=$!
sleep 5

if lsof -ti:8501 > /dev/null 2>&1 || ps -p $ST_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Streamlit UI started (PID: $ST_PID)${NC}"
    echo "  URL: http://localhost:8501"
    echo "  Logs: streamlit.log"
else
    echo -e "${YELLOW}⚠ Streamlit may still be starting...${NC}"
    echo "  Check logs: tail -20 streamlit.log"
fi
echo ""

# Step 6: Final status
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          ✅ ALL SERVICES STARTED SUCCESSFULLY ✅             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Service Status:"
echo "  • Database: $(brew services list | grep postgresql | grep started | awk '{print $2}' || echo 'Not running')"
echo "  • Background Service: $(pgrep -f background_service.py > /dev/null && echo 'RUNNING' || echo 'NOT RUNNING')"
echo "  • Streamlit UI: $(lsof -ti:8501 > /dev/null 2>&1 && echo 'RUNNING' || echo 'NOT RUNNING')"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Open your browser: http://localhost:8501"
echo ""
echo "📝 Monitor logs:"
echo "   tail -f background_service.log"
echo "   tail -f streamlit.log"
echo ""
echo "🛑 To stop all services:"
echo "   ./stop_all.sh"
echo "   (or: pkill -f background_service.py && kill \$(lsof -ti:8501))"
echo ""

