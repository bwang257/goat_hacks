#!/bin/bash

# MBTA Real-Time Transfer Helper - Startup Script

echo "================================================"
echo "  MBTA Real-Time Transfer Helper"
echo "================================================"
echo ""

# Set MBTA API Key
export MBTA_API_KEY='4bb94e38d4f7493baff2dff87960aa39'
export PATH="/Users/amansiddiqi/.nvm/versions/node/v24.13.0/bin:$PATH"

# Start backend
echo "Starting backend server..."
cd backend

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "  Using virtual environment"
fi

python3 main.py &
BACKEND_PID=$!
echo "✓ Backend started (PID: $BACKEND_PID)"

# Wait for backend to be ready
echo "Waiting for backend to initialize..."
sleep 3

# Start frontend
echo ""
echo "Starting frontend..."
cd ..
npm run dev &
FRONTEND_PID=$!
echo "✓ Frontend started (PID: $FRONTEND_PID)"

echo ""
echo "================================================"
echo "  Services are running!"
echo "================================================"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo ""
echo "  Press Ctrl+C to stop all services"
echo "================================================"
echo ""

# Wait for Ctrl+C
trap "echo ''; echo 'Stopping services...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '✓ All services stopped'; exit" INT

# Keep script running
wait
