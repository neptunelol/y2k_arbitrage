#!/bin/bash

# Shell script to start both Backend and Frontend in one single command.

# Function to clean up background processes on exit
cleanup() {
    echo ""
    echo "🛑 Stopping Y2K Arbitrage Platform..."
    kill 0 2>/dev/null || true
    pkill -P $$ 2>/dev/null || true
    exit 0
}

# Register trap for Ctrl+C (SIGINT) and exit (SIGTERM)
trap cleanup SIGINT SIGTERM EXIT

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Free up ports 8000 and 3000 if currently occupied
kill -9 $(lsof -t -i:8000) 2>/dev/null || true
kill -9 $(lsof -t -i:3000) 2>/dev/null || true

echo "============================================================"
echo "🚀 Starting Y2K Digital Camera Arbitrage Platform"
echo "============================================================"

# 1. Start Python Backend Daemon & API on Port 8000
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

echo "[1/2] Starting Python Backend & API (http://localhost:8000)..."
cd "$SCRIPT_DIR/backend"
python main.py &
BACKEND_PID=$!
cd "$SCRIPT_DIR"

# Give backend a moment to bind to port 8000
sleep 2

# 2. Start Next.js Command Center on Port 3000
echo "[2/2] Starting Next.js Command Center (http://localhost:3000)..."
cd "$SCRIPT_DIR/arbitrage_command_center"
npm run dev &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

echo "============================================================"
echo "✅ Both services running successfully!"
echo "   🖥️ Command Center: http://localhost:3000"
echo "   ⚡ Backend API:     http://localhost:8000"
echo "============================================================"
echo "Press Ctrl+C anytime to stop both services."
echo ""

# Wait for background jobs
wait
