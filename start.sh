#!/bin/bash

# LLM Council - Start script

echo "Starting LLM Council..."
echo ""

cd "$(dirname "$0")"  # Ensure we're in the project root

# Function to kill process on a given port
kill_port() {
    local port=$1
    local pid=$(lsof -ti :$port 2>/dev/null)
    if [ -n "$pid" ]; then
        echo "⚠️  Port $port is in use by PID $pid, killing..."
        kill -9 $pid 2>/dev/null
        sleep 1
    fi
}

# Clean up function
cleanup() {
    echo ""
    echo "Stopping servers..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 0
}

# Clean up ports before starting
kill_port 8001
kill_port 5173

# Start FalkorDB (Docker)
FALKORDB_CONTAINER="falkordb"
echo "Starting FalkorDB..."
if docker ps --format '{{.Names}}' | grep -q "^${FALKORDB_CONTAINER}$"; then
    echo "✓ FalkorDB container already running"
else
    if docker ps -a --format '{{.Names}}' | grep -q "^${FALKORDB_CONTAINER}$"; then
        docker start "$FALKORDB_CONTAINER" >/dev/null
    else
        docker run -d --name "$FALKORDB_CONTAINER" -p 6379:6379 falkordb/falkordb:latest >/dev/null
    fi
    echo "✓ FalkorDB started on redis://127.0.0.1:6379"
fi

# Start Graphiti MCP Server (Docker)
echo "Starting Graphiti MCP Server..."
./mcp_servers/graphiti-custom/start.sh
GRAPHITI_STARTED=$?

if [ $GRAPHITI_STARTED -ne 0 ]; then
    echo "⚠️  Graphiti MCP Server failed to start (continuing anyway)"
fi

# Start backend with uvicorn (suppress INFO-level websocket connection logs)
echo "Starting backend on http://localhost:8001..."
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8001 --log-level warning &
BACKEND_PID=$!

# Wait a bit for backend to start
sleep 3

# Start frontend
echo "Starting frontend on http://localhost:5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!

cd ..

echo ""
echo "✓ LLM Council is running!"
echo "  Backend:  http://localhost:8001"
echo "  Frontend: http://localhost:5173"
echo "  Graphiti: http://localhost:8000/mcp/"
echo ""
echo "Press ESC or Ctrl+C to stop servers (Graphiti container will keep running)"

# Trap signals
trap cleanup SIGINT SIGTERM

# Read keypresses in a loop
while true; do
    # Read a single character with 1 second timeout
    if read -rsn1 -t 1 key; then
        # Check for ESC (octal 033)
        if [[ "$key" == $'\e' ]]; then
            cleanup
        fi
    fi
    
    # Check if backend or frontend processes are still running
    if ! kill -0 $BACKEND_PID 2>/dev/null && ! kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "Processes terminated"
        exit 1
    fi
done
