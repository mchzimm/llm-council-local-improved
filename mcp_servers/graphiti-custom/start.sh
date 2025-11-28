#!/bin/bash

# Graphiti Custom MCP Server - Start script
# Builds and runs the custom Graphiti MCP server with LM Studio support
# Configuration is loaded from graphiti_config.json

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER_NAME="llm-council-mcp"
IMAGE_NAME="graphiti-custom"
CONFIG_FILE="$SCRIPT_DIR/graphiti_config.json"

echo "🚀 Starting Graphiti Custom MCP Server..."
echo ""

cd "$SCRIPT_DIR"

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Configuration file not found: $CONFIG_FILE"
    exit 1
fi

# Generate config.yaml and .env from JSON config
echo "📝 Generating configuration from graphiti_config.json..."
python3 generate_config.py
if [ $? -ne 0 ]; then
    echo "❌ Failed to generate configuration"
    exit 1
fi

# Source the generated environment variables
source "$SCRIPT_DIR/.env"

# Extract values from JSON for display
LLM_MODEL=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c['llm']['model'])")
LLM_URL=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c['llm']['base_url'])")
EMBEDDER_MODEL=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c['embedder']['model'])")
DB_URI=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c['database']['uri'])")

# Stop and remove existing container if running
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "⚠️  Stopping existing container: $CONTAINER_NAME"
    docker stop "$CONTAINER_NAME" 2>/dev/null
    docker rm "$CONTAINER_NAME" 2>/dev/null
fi

# Build the image if it doesn't exist or if files changed
echo "📦 Building Docker image: $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" .

if [ $? -ne 0 ]; then
    echo "❌ Failed to build Docker image"
    exit 1
fi

# Run the container with environment variables from .env
echo "🐳 Starting container: $CONTAINER_NAME..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -p 8000:8000 \
    -e OPENAI_API_KEY="$OPENAI_API_KEY" \
    -e OPENAI_BASE_URL="$OPENAI_BASE_URL" \
    -e EMBEDDER_API_KEY="$EMBEDDER_API_KEY" \
    -e EMBEDDER_BASE_URL="$EMBEDDER_BASE_URL" \
    -e EMBEDDER_DIM="$EMBEDDER_DIM" \
    --restart unless-stopped \
    "$IMAGE_NAME"

if [ $? -ne 0 ]; then
    echo "❌ Failed to start container"
    exit 1
fi

# Wait for server to be ready
echo "⏳ Waiting for server to start..."
sleep 5

# Check if container is running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo ""
    echo "✅ Graphiti MCP Server is running!"
    echo "   Container: $CONTAINER_NAME"
    echo "   MCP Endpoint: http://localhost:8000/mcp/"
    echo "   LLM: $LLM_MODEL @ $LLM_URL"
    echo "   Embedder: $EMBEDDER_MODEL @ $EMBEDDER_BASE_URL"
    echo "   Database: FalkorDB @ $DB_URI"
    echo ""
    echo "📋 View logs: docker logs -f $CONTAINER_NAME"
    echo "🛑 Stop: docker stop $CONTAINER_NAME"
else
    echo "❌ Container failed to start. Check logs:"
    docker logs "$CONTAINER_NAME"
    exit 1
fi
