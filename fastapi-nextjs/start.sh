#!/bin/bash
# Quick start script for FastAPI + Next.js

echo "🚀 Starting Option Chain Analysis - FastAPI + Next.js Version"
echo "=============================================================="
echo ""

# Check if backend dependencies installed
if [ ! -f "backend/main.py" ]; then
    echo "❌ Backend files not found!"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found! Please install Node.js 18+ from https://nodejs.org"
    exit 1
fi

# Install backend dependencies
echo "📦 Installing backend dependencies..."
cd backend
pip install -r requirements.txt

# Start FastAPI backend in background
echo "🔧 Starting FastAPI backend (port 8000)..."
python main.py &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

cd ../frontend

# Install frontend dependencies if not exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing frontend dependencies (this may take a few minutes)..."
    npm install
fi

# Start Next.js frontend
echo "🎨 Starting Next.js frontend (port 3000)..."
npm run dev &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

echo ""
echo "✅ Services started successfully!"
echo ""
echo "📊 Access the dashboard at: http://localhost:3000"
echo "📡 API documentation at: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for interrupt
trap "echo ''; echo '🛑 Stopping services...'; kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
