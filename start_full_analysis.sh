#!/bin/bash
# Start Streamlit Option Chain Analysis (Full Features)

set -e

echo "🚀 Starting Full Option Chain Analysis (Streamlit)"
echo "=================================================="

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if virtual environment exists
if [ ! -d "../.venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found in parent directory${NC}"
    exit 1
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source ../.venv/bin/activate

# Check database connection
echo "🔍 Checking database connection..."
if ! psql -d optionchain -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${RED}❌ Database connection failed!${NC}"
    echo "Please ensure PostgreSQL/TimescaleDB is running:"
    echo "  brew services start postgresql@14"
    exit 1
fi

echo -e "${GREEN}✓ Database connection OK${NC}"

# Kill any existing processes
echo "🛑 Stopping any existing services..."
pkill -f "streamlit run optionchain" 2>/dev/null || true
pkill -f "python.*background_service.py" 2>/dev/null || true
pkill -f "python.*dashboard_app.py" 2>/dev/null || true
sleep 2

# Create logs directory
mkdir -p logs

# Start background service (data collection)
echo "🔄 Starting background data collection service..."
echo "   • Force mode: Runs even when market is closed (for testing)"
nohup python3 background_service.py --interval 180 --force > logs/background_service.log 2>&1 &
BG_PID=$!
echo -e "${GREEN}✓ Background service started (PID: $BG_PID)${NC}"
echo "$BG_PID" > logs/background.pid

# Wait for background service to initialize
sleep 3

# Check if background service is still running
if ! ps -p $BG_PID > /dev/null; then
    echo -e "${RED}❌ Background service failed to start!${NC}"
    echo "Check logs/background_service.log for details"
    tail -20 logs/background_service.log
    exit 1
fi

# Start Streamlit app with full features
echo "🎨 Starting Streamlit Option Chain Analysis..."
echo "   • Full bucket summaries"
echo "   • PCR analysis (ITM/OTM/Overall)"
echo "   • Gamma exposure analysis"
echo "   • Option chain table with Greeks"
echo "   • Sentiment analysis"
echo "   • Position tracking"
echo ""

streamlit run optionchain.py --server.port=8502 --server.headless=true > logs/streamlit.log 2>&1 &
STREAMLIT_PID=$!
echo -e "${GREEN}✓ Streamlit started (PID: $STREAMLIT_PID)${NC}"
echo "$STREAMLIT_PID" > logs/streamlit.pid

# Wait for Streamlit to start
sleep 5

# Check if Streamlit is still running
if ! ps -p $STREAMLIT_PID > /dev/null; then
    echo -e "${RED}❌ Streamlit failed to start!${NC}"
    echo "Check logs/streamlit.log for details"
    tail -20 logs/streamlit.log
    exit 1
fi

echo ""
echo "========================================="
echo -e "${GREEN}✓ Full System Started Successfully!${NC}"
echo "========================================="
echo ""
echo "📊 Streamlit UI (Full Features): http://localhost:8502"
echo "📝 Logs directory: ./logs/"
echo ""
echo "🔍 Monitor logs:"
echo "   • Background: tail -f logs/background_service.log"
echo "   • Streamlit:  tail -f logs/streamlit.log"
echo ""
echo "⏹️  To stop:"
echo "   • Run: ./stop_system.sh"
echo "   • Or manually: kill $BG_PID $STREAMLIT_PID"
echo ""
echo "✨ Features Available:"
echo "   ✓ Bucket Summaries (ITM/OTM for CE/PE)"
echo "   ✓ PCR Analysis (OI/ChgOI/Volume)"
echo "   ✓ Gamma Exposure & GEX Analysis"
echo "   ✓ Option Chain Table with all Greeks"
echo "   ✓ Sentiment Score with breakdown"
echo "   ✓ Position Tracking (Long/Short Build/Covering)"
echo "   ✓ ITM Filtering (3/5/7 strikes)"
echo "   ✓ Real-time auto-refresh"
echo ""

# Monitor for a few seconds
echo "🔍 Monitoring services for 10 seconds..."
for i in {1..10}; do
    if ! ps -p $BG_PID > /dev/null; then
        echo -e "${RED}❌ Background service died!${NC}"
        tail -30 logs/background_service.log
        exit 1
    fi
    if ! ps -p $STREAMLIT_PID > /dev/null; then
        echo -e "${RED}❌ Streamlit died!${NC}"
        tail -30 logs/streamlit.log
        exit 1
    fi
    echo -n "."
    sleep 1
done

echo ""
echo -e "${GREEN}✓ All services running healthy${NC}"
echo "🎉 System ready! Open http://localhost:8502 in your browser"
echo ""
echo "💡 TIP: For simple dashboard, use ./start_system.sh (port 8501)"
echo "        For full analysis, use this (port 8502)"
echo ""
