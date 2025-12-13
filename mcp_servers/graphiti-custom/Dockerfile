FROM python:3.12-slim

WORKDIR /app

# Install git
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Clone graphiti
RUN git clone --depth 1 https://github.com/getzep/graphiti.git /app/graphiti

WORKDIR /app/graphiti/mcp_server

# Copy custom LM Studio client and patch scripts
COPY lmstudio_client.py /app/graphiti/mcp_server/src/
COPY patch_factories.py /app/
COPY patch_edge_logging.py /app/

# Run the patch scripts
RUN python /app/patch_factories.py
RUN python /app/patch_edge_logging.py

# Install dependencies
RUN pip install --no-cache-dir uv && \
    uv pip install --system -e . && \
    uv pip install --system graphiti-core[falkordb]

# Copy custom config
COPY config.yaml /app/graphiti/mcp_server/config/config.yaml

# Set environment variables for LM Studio (use host.docker.internal for macOS Docker)
ENV OPENAI_BASE_URL=http://host.docker.internal:11434/v1
ENV OPENAI_API_KEY=lms

EXPOSE 8000

# Run the server
CMD ["python", "-m", "main"]
