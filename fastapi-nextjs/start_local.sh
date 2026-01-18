#!/bin/bash

# Quick start script for local testing
# This will start both backend and frontend in separate terminal windows

echo "🚀 Starting Local Development Environment..."
echo ""

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# Check if we're on macOS (for open command)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - use open command to create new terminal windows
    echo "📦 Starting Backend (Terminal 1)..."
    osascript -e "tell application 'Terminal' to do script \"cd '$BACKEND_DIR' && python3 main.py\""
    
    sleep 2
    
    echo "📦 Starting Frontend (Terminal 2)..."
    osascript -e "tell application 'Terminal' to do script \"cd '$FRONTEND_DIR' && npm run dev\""
    
    echo ""
    echo "✅ Both services starting in separate terminal windows"
    echo ""
    echo "🌐 Frontend: http://localhost:3000"
    echo "🔧 Backend:  http://localhost:8000"
    echo ""
    echo "Press Ctrl+C in each terminal to stop the services"
else
    # Linux/Other - run in background
    echo "📦 Starting Backend..."
    cd "$BACKEND_DIR"
    python3 main.py > /tmp/backend.log 2>&1 &
    BACKEND_PID=$!
    echo "Backend PID: $BACKEND_PID"
    
    sleep 2
    
    echo "📦 Starting Frontend..."
    cd "$FRONTEND_DIR"
    npm run dev > /tmp/frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "Frontend PID: $FRONTEND_PID"
    
    echo ""
    echo "✅ Both services started in background"
    echo ""
    echo "🌐 Frontend: http://localhost:3000"
    echo "🔧 Backend:  http://localhost:8000"
    echo ""
    echo "Logs:"
    echo "  Backend:  tail -f /tmp/backend.log"
    echo "  Frontend: tail -f /tmp/frontend.log"
    echo ""
    echo "To stop:"
    echo "  kill $BACKEND_PID $FRONTEND_PID"
fi
