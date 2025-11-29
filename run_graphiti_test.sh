#!/bin/bash
#
# run_graphiti_test.sh - Run Graphiti MCP server tests
#
# This script:
# 1. Starts/restarts the Graphiti MCP server (rebuilds container with latest config)
# 2. Waits for server to be ready
# 3. Runs the Graphiti test suite
# 4. Reports results
#
# Usage: ./run_graphiti_test.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "GRAPHITI MCP SERVER TEST RUNNER"
echo "============================================================"
echo ""

# Step 1: Start/restart Graphiti MCP server
echo "[1/3] Starting Graphiti MCP server..."
echo "      (This will rebuild the container with latest graphiti_config.json)"
echo ""

if ! ./mcp_servers/graphiti-custom/start.sh; then
    echo ""
    echo "❌ Failed to start Graphiti MCP server"
    echo "   Check Docker is running and FalkorDB is accessible"
    exit 1
fi

echo ""

# Step 2: Wait for server to be fully ready
echo "[2/3] Waiting for Graphiti server to be fully ready..."
sleep 5

# Check health endpoint
MAX_ATTEMPTS=10
ATTEMPT=1
while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    if curl -s -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "      ✅ Graphiti server is ready"
        break
    fi
    echo "      Attempt $ATTEMPT/$MAX_ATTEMPTS - waiting..."
    sleep 3
    ATTEMPT=$((ATTEMPT + 1))
done

if [ $ATTEMPT -gt $MAX_ATTEMPTS ]; then
    echo "      ❌ Graphiti server did not become ready"
    echo "      Check: docker logs llm-council-mcp"
    exit 1
fi

echo ""

# Step 3: Run the test suite
echo "[3/3] Running Graphiti test suite..."
echo "      Using group_id: test_graphiti (separate from production)"
echo ""
echo "============================================================"

uv run python -m tests.test_graphiti
TEST_RESULT=$?

echo ""
echo "============================================================"

if [ $TEST_RESULT -eq 0 ]; then
    echo "✅ Graphiti tests completed successfully"
else
    echo "❌ Graphiti tests failed (exit code: $TEST_RESULT)"
fi

echo ""
echo "📋 View Graphiti logs: docker logs -f llm-council-mcp"
echo "🛑 Stop Graphiti: docker stop llm-council-mcp"
echo "============================================================"

exit $TEST_RESULT
