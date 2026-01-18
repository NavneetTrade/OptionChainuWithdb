#!/bin/bash

# Test script for local development
# This script tests if the backend and frontend can start properly

echo "🧪 Testing Local Setup..."
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Check if backend dependencies are installed
echo "1️⃣  Checking backend dependencies..."
cd backend
if python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo -e "${GREEN}✓ Backend dependencies installed${NC}"
else
    echo -e "${RED}✗ Backend dependencies missing. Install with: pip install -r requirements.txt${NC}"
    exit 1
fi
cd ..

# Test 2: Check if frontend dependencies are installed
echo "2️⃣  Checking frontend dependencies..."
cd frontend
if [ -d "node_modules" ]; then
    echo -e "${GREEN}✓ Frontend dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠ Frontend dependencies missing. Install with: npm install${NC}"
fi
cd ..

# Test 3: Check if backend can import modules
echo "3️⃣  Testing backend imports..."
cd backend
if python3 -c "
import sys
import os
parent_dir = os.path.abspath(os.path.join(os.path.dirname('.'), '..'))
sys.path.insert(0, parent_dir)
try:
    from database import TimescaleDBManager
    from upstox_api import UpstoxAPI
    from token_manager import get_token_manager
    print('✓ Backend imports successful')
except ImportError as e:
    print(f'✗ Backend import error: {e}')
    sys.exit(1)
" 2>&1; then
    echo -e "${GREEN}✓ Backend imports successful${NC}"
else
    echo -e "${RED}✗ Backend import failed${NC}"
    exit 1
fi
cd ..

# Test 4: Check if API endpoint exists
echo "4️⃣  Checking API endpoint structure..."
if grep -q "@app.get(\"/api/gamma/all\")" backend/main.py; then
    echo -e "${GREEN}✓ /api/gamma/all endpoint found${NC}"
else
    echo -e "${RED}✗ /api/gamma/all endpoint missing${NC}"
    exit 1
fi

# Test 5: Check if useAutoRefresh hook exists
echo "5️⃣  Checking frontend auto-refresh hook..."
if [ -f "frontend/hooks/useAutoRefresh.ts" ]; then
    echo -e "${GREEN}✓ useAutoRefresh hook found${NC}"
else
    echo -e "${RED}✗ useAutoRefresh hook missing${NC}"
    exit 1
fi

# Test 6: Check if WebSocket code is removed
echo "6️⃣  Verifying WebSocket removal..."
if grep -q "WebSocket\|websocket" backend/main.py 2>/dev/null; then
    echo -e "${YELLOW}⚠ WebSocket references still found in backend${NC}"
else
    echo -e "${GREEN}✓ WebSocket code removed from backend${NC}"
fi

if [ -f "frontend/hooks/useWebSocket.ts" ]; then
    echo -e "${YELLOW}⚠ useWebSocket.ts still exists${NC}"
else
    echo -e "${GREEN}✓ WebSocket hook removed from frontend${NC}"
fi

echo ""
echo -e "${GREEN}✅ All checks passed!${NC}"
echo ""
echo "📋 To start the services:"
echo "   Backend:  cd backend && python3 main.py"
echo "   Frontend: cd frontend && npm run dev"
echo ""
echo "🌐 Then open: http://localhost:3000"
