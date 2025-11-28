# Graphiti Custom MCP Server

Custom fork of Graphiti MCP server with LM Studio support via custom `LMStudioClient`.

## Key Features

- **Strict JSON Schema** - Uses `additionalProperties: false` for LM Studio compatibility
- **Automatic retry** - Retries failed JSON parsing with error context
- **FalkorDB support** - Configured for FalkorDB at `redis://192.168.1.111:6379`
- **JSON Configuration** - Easy configuration via `graphiti_config.json`

## Changes from upstream

1. Added `LMStudioClient` - Custom LLM client with strict JSON schema support
2. Added `lmstudio` provider option in `LLMClientFactory`
3. Added `openai_generic` provider for standard OpenAI-compatible embedders
4. JSON-based configuration system

## Files

- `graphiti_config.json` - **Main configuration file** (edit this)
- `generate_config.py` - Generates config.yaml and .env from JSON
- `lmstudio_client.py` - Custom LLM client with strict JSON schema
- `patch_factories.py` - Patch to add lmstudio/openai_generic providers
- `config.yaml` - Auto-generated from graphiti_config.json (don't edit)
- `Dockerfile` - Build container with patches applied
- `start.sh` - Build and run script

## Configuration

Edit `graphiti_config.json` to configure LLM, embedder, and database:

```json
{
  "llm": {
    "provider": "lmstudio",
    "model": "qwen2.5-14b-instruct",
    "api_key": "lms",
    "base_url": "http://192.168.1.111:11434/v1",
    "temperature": 0.0,
    "max_tokens": 16384
  },
  "embedder": {
    "provider": "openai_generic",
    "model": "text-embedding-nomic-embed-text-v1.5@f16",
    "api_key": "lms",
    "base_url": "http://192.168.1.111:11434/v1",
    "embedding_dim": 768
  },
  "database": {
    "provider": "falkordb",
    "uri": "redis://192.168.1.111:6379",
    "password": "",
    "database": "graphiti"
  },
  "server": {
    "transport": "http",
    "host": "0.0.0.0",
    "port": 8000
  },
  "graphiti": {
    "group_id": "main"
  }
}
```

### Supported Providers

**LLM Providers:**
- `lmstudio` - LM Studio with strict JSON schema support
- `openai` - OpenAI API
- `anthropic` - Anthropic API
- `gemini` - Google Gemini

**Embedder Providers:**
- `openai_generic` - Any OpenAI-compatible endpoint (LM Studio, Ollama, etc.)
- `openai` - OpenAI API
- `voyage` - Voyage AI

**Database Providers:**
- `falkordb` - FalkorDB (recommended)
- `neo4j` - Neo4j

## Build & Run

```bash
cd mcp_servers/graphiti-custom

# Option 1: Use start script (recommended)
./start.sh

# Option 2: Manual build and run
python3 generate_config.py  # Generate config from JSON
docker build -t graphiti-custom .
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=lms \
  -e OPENAI_BASE_URL=http://192.168.1.111:11434/v1 \
  -e EMBEDDER_API_KEY=lms \
  -e EMBEDDER_BASE_URL=http://192.168.1.111:11434/v1 \
  -e EMBEDDER_DIM=768 \
  graphiti-custom
```

## JSON Schema Format

The `LMStudioClient` generates strict JSON schemas like:

```json
{
  "type": "json_schema",
  "json_schema": {
    "name": "ExtractedEntities",
    "strict": true,
    "schema": {
      "type": "object",
      "required": ["extracted_entities"],
      "additionalProperties": false,
      "properties": {
        "extracted_entities": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "entity_type_id"],
            "additionalProperties": false,
            "properties": {
              "name": {"type": "string"},
              "entity_type_id": {"type": "integer"}
            }
          }
        }
      }
    }
  }
}
```

## Testing

After running, test with:

```bash
cd /Users/max/llm-council
uv run python -m tests.test_graphiti
```

## Troubleshooting

### LLM returned invalid duplicate_facts idx values

This warning indicates the LLM returned out-of-range indices for fact deduplication. This is typically caused by:
1. Local LLM not following JSON schema precisely
2. Temperature too high (use 0.0)
3. Model not capable of structured JSON output

**Solution:** Use a more capable model (e.g., qwen2.5-14b-instruct or larger) and ensure temperature is set to 0.0.
