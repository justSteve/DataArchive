#!/bin/bash
# Development startup script
# Runs both API server and frontend dev server concurrently

echo "=========================================="
echo "DataArchive Development Environment"
echo "=========================================="
echo ""
echo "Starting services..."
echo ""

# Function to cleanup on exit
cleanup() {
  echo ""
  echo "Shutting down services..."
  kill $API_PID $FRONTEND_PID 2>/dev/null
  exit 0
}

trap cleanup SIGINT SIGTERM

# Start API server in background
echo "[1/2] Starting API server (port 3001)..."
npm run api &
API_PID=$!

# Wait a moment for API to start
sleep 2

# Start frontend dev server in background
echo "[2/2] Starting frontend dev server (port 5173)..."
npm run dev &
FRONTEND_PID=$!

echo ""
echo "=========================================="
echo "✓ Services started successfully!"
echo "=========================================="
echo ""
echo "Access the application at:"
echo "  Frontend: http://localhost:5173"
echo "  API:      http://localhost:3001"
echo "  Health:   http://localhost:3001/api/health"
echo ""
echo "Press Ctrl+C to stop all services"
echo "=========================================="
echo ""

# Wait for processes
wait
