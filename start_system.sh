#!/bin/bash
# Complete System Startup Script with Rate Limit Protection
# Starts background service + modern HTML dashboard

set -e  # Exit on error

echo "🚀 Starting Option Chain Analysis System"
echo "========================================"

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0.31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found. Creating...${NC}"
    python3 -m venv .venv
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source .venv/bin/activate

# Install/upgrade required packages
echo "📥 Installing required packages..."
pip install -q --upgrade pip
pip install -q -r requirements_dashboard.txt || {
    echo -e "${RED}❌ Failed to install packages${NC}"
    exit 1
}

# Check if PostgreSQL/TimescaleDB is running
echo "🔍 Checking database connection..."
if ! psql -d optionchain -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${RED}❌ Database connection failed!${NC}"
    echo "Please ensure PostgreSQL/TimescaleDB is running:"
    echo "  brew services start postgresql@14"
    exit 1
fi

echo -e "${GREEN}✓ Database connection OK${NC}"

# Add database indexes if not exist (with timeout protection)
echo "🔧 Optimizing database (adding indexes)..."
psql -d optionchain -c "
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_oc_inst_time ON option_chain_data(instrument_key, timestamp DESC);
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_oc_sym_exp ON option_chain_data(symbol, expiry_date);
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sent_sym_time ON sentiment_scores(symbol, timestamp DESC);
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gamma_sym_time ON gamma_exposure_history(symbol, timestamp DESC);
" > /dev/null 2>&1 &
INDEX_PID=$!

# Wait for indexes (with timeout)
sleep 2
if ps -p $INDEX_PID > /dev/null; then
    echo -e "${YELLOW}⚠️  Index creation in progress (running in background)...${NC}"
else
    echo -e "${GREEN}✓ Database indexes OK${NC}"
fi

# Kill any existing processes
echo "🛑 Stopping any existing services..."
pkill -f "python.*background_service.py" 2>/dev/null || true
pkill -f "streamlit run" 2>/dev/null || true
lsof -ti:8502 | xargs kill -9 2>/dev/null || true
sleep 2

# Create logs directory
mkdir -p logs

# Start background service with hybrid mode
echo "🔄 Starting background data collection service..."
echo "   • HYBRID MODE: Real-time + Periodic"
echo "   • Indices: WebSocket real-time streaming"
echo "   • Stocks: REST API 3-minute refresh"
echo "   • Daily expiry cache"
echo ""

nohup python3 background_service.py --interval 180 > logs/background_service.log 2>&1 &
BG_PID=$!
echo -e "${GREEN}✓ Background service started (PID: $BG_PID)${NC}"

# Wait a moment for background service to initialize
sleep 3

# Check if background service is still running
if ! ps -p $BG_PID > /dev/null; then
    echo -e "${RED}❌ Background service failed to start!${NC}"
    echo "Check logs/background_service.log for details"
    tail -20 logs/background_service.log
    exit 1
fi

# Start Streamlit dashboard
echo "🌐 Starting Streamlit dashboard..."
echo "   • Real-time auto-refresh"
echo "   • Comprehensive option chain analysis"
echo "   • Multi-tab interface"
echo ""

nohup streamlit run optionchain.py --server.port 8502 --server.headless true > logs/dashboard.log 2>&1 &
DASH_PID=$!
echo -e "${GREEN}✓ Dashboard started (PID: $DASH_PID)${NC}"

# Wait for dashboard to start
sleep 5

# Check if dashboard is accessible
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8502 | grep -q "200"; then
    echo -e "${GREEN}✓ Dashboard is accessible${NC}"
else
    echo -e "${RED}❌ Dashboard failed to start!${NC}"
    echo "Check logs/dashboard.log for details"
    tail -20 logs/dashboard.log
    exit 1
fi

# Save PIDs for later
echo "$BG_PID" > logs/background.pid
echo "$DASH_PID" > logs/dashboard.pid

# Display status and URLs
echo ""
echo "========================================="
echo -e "${GREEN}✓ System Started Successfully!${NC}"
echo "========================================="
echo ""
echo "📊 Dashboard URL:  http://localhost:8502"
echo "📝 Logs directory: ./logs/"
echo ""
echo "🔍 Monitor logs:"
echo "   • Background: tail -f logs/background_service.log"
echo "   • Dashboard:  tail -f logs/dashboard.log"
echo ""
echo "⏹️  To stop:"
echo "   • Run: ./stop_system.sh"
echo "   • Or manually: kill $BG_PID $DASH_PID"
echo ""
echo "⚠️  Rate Limit Protection Enabled:"
echo "   • Max 2 concurrent API calls"
echo "   • 500ms delay between requests"
echo "   • Automatic retry with exponential backoff"
echo "   • If you see rate limit errors, they will auto-recover"
echo ""

# Monitor for a few seconds
echo "🔍 Monitoring services for 10 seconds..."
for i in {1..10}; do
    if ! ps -p $BG_PID > /dev/null; then
        echo -e "${RED}❌ Background service died!${NC}"
        tail -30 logs/background_service.log
        exit 1
    fi
    # Check if streamlit port is still accessible
    if ! lsof -ti:8502 > /dev/null 2>&1; then
        echo -e "${RED}❌ Dashboard died!${NC}"
        tail -30 logs/dashboard.log
        exit 1
    fi
    echo -n "."
    sleep 1
done

echo ""
echo -e "${GREEN}✓ All services running healthy${NC}"
echo "🎉 System ready! Open http://localhost:8502 in your browser"
echo ""
