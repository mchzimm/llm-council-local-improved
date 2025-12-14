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

# Track started Docker containers
STARTED_CONTAINERS=()

# Clean up function - stops and removes all processes and Docker containers we started
cleanup() {
    echo ""
    echo "Stopping servers..."
    
    # Stop backend and frontend first
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    
    # Stop and remove Docker containers in REVERSE order (dependencies first)
    # Graphiti depends on FalkorDB, so Graphiti must be stopped first
    if [ ${#STARTED_CONTAINERS[@]} -gt 0 ]; then
        echo "Stopping and removing Docker containers (in reverse order)..."
        
        # Reverse the array
        reversed=()
        for ((i=${#STARTED_CONTAINERS[@]}-1; i>=0; i--)); do
            reversed+=("${STARTED_CONTAINERS[$i]}")
        done
        
        for container in "${reversed[@]}"; do
            if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
                echo "  Stopping $container (waiting for graceful shutdown)..."
                # Use timeout to allow graceful shutdown (e.g., pending memory writes)
                docker stop --time 10 "$container" >/dev/null 2>&1
                docker rm "$container" >/dev/null 2>&1
            fi
        done
        echo "✓ Docker containers removed"
    fi
    flush(){ while read -N 1 -t 0.01; do :; done }
    echo -e "\n"
    exit 0
}

# Clean up ports before starting
kill_port 8001
kill_port 5173

# Start FalkorDB (Docker)
FALKORDB_CONTAINER="falkordb"
echo "Starting FalkorDB..."
FALKORDB_WAS_RUNNING=false
if docker ps --format '{{.Names}}' | grep -q "^${FALKORDB_CONTAINER}$"; then
    echo "✓ FalkorDB container already running"
    FALKORDB_WAS_RUNNING=true
else
    if docker ps -a --format '{{.Names}}' | grep -q "^${FALKORDB_CONTAINER}$"; then
        docker start "$FALKORDB_CONTAINER" >/dev/null
    else
        docker run -d --name "$FALKORDB_CONTAINER" -v falkordb_data:/var/lib/falkordb/data -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest >/dev/null
    fi
    echo "✓ FalkorDB started on redis://127.0.0.1:6379"
    STARTED_CONTAINERS+=("$FALKORDB_CONTAINER")
fi

# Start Graphiti MCP Server (Docker)
echo "Starting Graphiti MCP Server..."
GRAPHITI_CONTAINER="llm-council-mcp"
GRAPHITI_WAS_RUNNING=false
if docker ps --format '{{.Names}}' | grep -q "^${GRAPHITI_CONTAINER}$"; then
    GRAPHITI_WAS_RUNNING=true
fi

./mcp_servers/graphiti-custom/start.sh
GRAPHITI_STARTED=$?

if [ $GRAPHITI_STARTED -ne 0 ]; then
    echo "⚠️  Graphiti MCP Server failed to start (continuing anyway)"
else
    # Track the container if we started it (wasn't running before)
    if [ "$GRAPHITI_WAS_RUNNING" = false ]; then
        STARTED_CONTAINERS+=("$GRAPHITI_CONTAINER")
    fi
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
echo "Press ESC or Ctrl+C to stop all servers and remove Docker containers"

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
