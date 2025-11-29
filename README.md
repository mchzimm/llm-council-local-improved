**NOTE: Based on `https://github.com/karpathy/llm-council` but has been modified to access LLMs via OpenAI API base. API keys are optional (focus is on local inference). Features per-model configuration with Parameter Resolution Logic: per-model values override main values override defaults.**

# LLM Council

![llmcouncil](header.jpg)

The idea of this repo is that instead of asking a question to your favorite LLM provider (e.g. OpenAI GPT 5.1, Google Gemini 3.0 Pro, Anthropic Claude Sonnet 4.5, xAI Grok 4, eg.c), you can group them into your "LLM Council". This repo is a simple, local web app that essentially looks like ChatGPT except it uses LM Studio (or Ollama, etc.) to send your query to multiple LLMs, it then asks them to review and rank each other's work across multiple deliberation rounds, and finally a Chairman LLM produces the final response.

The UI and UX have been significantly improved with features like real-time streaming, conversation management, automatic title generation, and enhanced visual feedback.

In a bit more detail, here is what happens when you submit a query:

1. **Stage 0: Message Classification** (NEW in v0.8.0). The Chairman analyzes your message to determine if it requires deliberation. Simple factual questions and casual chat get direct answers; complex questions requiring opinions, comparisons, or feedback go through the full council process.
2. **Stage 1: First opinions**. The user query is given to all LLMs individually, and the responses are collected. The individual responses are shown in a "tab view", so that the user can inspect them all one by one.
3. **Stage 2: Multi-Round Deliberation**. Each individual LLM is given the responses of the other LLMs. Under the hood, the LLM identities are anonymized so that the LLM can't play favorites when judging their outputs. The LLM is asked to rank them in accuracy and insight. In multi-round mode (configurable), models can refine their responses based on peer feedback across multiple rounds of review.
4. **Stage 3: Final response**. The designated Chairman of the LLM Council takes all of the model's responses and rankings from all deliberation rounds and compiles them into a single final answer that is presented to the user.

## Key Features

### Current Release (v0.23.0)
- **MCP Tool Execution Time**: Display execution time for MCP tool calls in tool result card

### Previous Release (v0.22.0)
- **Duplicate Conversation Cleanup**: UI button to find and delete duplicate conversations
  - Automatically detects conversations with identical user queries (same count and content)
  - "Clean Duplicates" button appears in sidebar when duplicates exist
  - Keeps newest copy of each duplicate group, moves others to recycle bin
  - Shows count of removable duplicates in the button

### Previous Release (v0.21.0)
- **LLM-Based Tool Confidence Routing**: Intelligent tool selection using expectation analysis
  - Step 1: LLM analyzes user expectations and determines data types needed
  - Step 2: Deterministic mapping from data types to appropriate tools
  - Replaces hardcoded keyword lists (WEBSEARCH_KEYWORDS, GEOLOCATION_KEYWORDS)
  - Data type mappings: current_time, location, news, weather, calculation, web_content
  - Confidence threshold (0.5) for tool selection decisions
  - More flexible and extensible than keyword matching

### Previous Release (v0.20.0)
- **Graphiti Memory Integration**: Persistent memory with confidence-based fast-path responses
  - Records all messages (user, council members, chairman) to Graphiti knowledge graph
  - Memory-based response path when confidence exceeds configurable threshold (default 80%)
  - Configurable confidence model (defaults to chairman if not specified)
  - Age-weighted confidence scoring for memory freshness
  - Graceful degradation when Graphiti unavailable
  - New `/api/memory/status` endpoint for memory service status
  - Non-blocking async recording for minimal latency impact

### Previous Release (v0.18.0)
- **Graphiti Knowledge Graph Integration**: Persistent memory for AI agents
  - Connect to external Graphiti MCP server (http://localhost:8000/mcp)
  - Episode management: add memories, retrieve episodes, delete data
  - Entity search: find nodes and facts in the knowledge graph
  - Session-based HTTP MCP protocol with SSE response support
  - 9 new tools for knowledge graph operations

### Previous Release (v0.17.0)
- **External MCP Server Support**: Install MCP servers from online sources
  - New `transport` config field: `"stdio"` for external servers, `"http"` for local (default)
  - Support for npx-based MCP servers (e.g., `@modelcontextprotocol/server-*`)
  - Integrated `sequential-thinking` server for dynamic problem-solving
  - Easy addition of servers from mcpservers.org and GitHub MCP repos

### Previous Release (v0.16.0)
- **Intelligent Prompt Engineering**: Dynamic prompt generation system
  - `prompt_engineer` model config (defaults to chairman if not specified)
  - Prompt library (`data/prompt_library.json`, `data/prompt_library.md`) for caching proven prompts
  - Automatic prompt generation for tool output extraction based on query type
  - Category-based prompt matching (news, weather, location, datetime, etc.)
  - Success rate tracking for prompt optimization over time

### Previous Release (v0.15.7)
- **Websearch POST Fix**: SearXNG now queried via POST instead of GET for proper results
- **Classification Improvements**: Better `requires_tools` detection for geolocation, weather, and news queries
- **Result Interpretation**: Improved guidance for extracting actual content from search snippets

### Previous Release (v0.14.0)
- **Formatter Model for Direct Responses**: Two-step response generation
  - Chairman generates initial response content
  - Configurable formatter model improves formatting and readability
  - Falls back to chairman if formatter not configured

### Previous Release (v0.12.0)
- **MCP Status Indicator**: Visual MCP server status in sidebar header
  - "MCP" badge next to "LLM Council" title with blue/grey styling
  - Hover overlay showing all MCP servers with status indicators
  - Red (offline), yellow (busy), green (available) status colors
  - Secondary hover overlay showing server tools with in-use highlighting
  - Real-time metrics: server count, tool count, active tools

### Previous Release (v0.11.0)
- **System Timezone MCP Server**: New MCP server for retrieving timezone information
  - Tool: `get-timezone-list` returns system timezone and complete tz database list
  - Parses Wikipedia's timezone database for comprehensive coverage (500+ timezones)
  - 24-hour caching for efficiency

### Previous Release (v0.10.0)
- **System Geo-Location MCP Server**: New MCP server for retrieving location based on IP
  - Tool: `get-system-geo-location` returns City, State/Region, Postal Code, Country
  - Uses whatismyip.com for IP-based geolocation
  - No external API keys required

### Previous Release (v0.9.0)
- **Retrieve Web Page MCP Server**: New MCP server for fetching HTML content from URLs
  - Tool: `get-page-from-url` retrieves full page HTML
  - Foundation for geo-location and timezone MCP servers
  - Handles HTTP errors, URL errors, and timeouts (30s)

### Previous Release (v0.8.0)
- **Intelligent Message Routing**: Chairman classifies messages before deliberation
  - Classifies messages as factual, chat, or deliberation-required
  - Direct fast answers for simple questions (skips council)
  - Full 3-stage deliberation for complex questions
  - Visual classification badges show response type
  - Blue styling for direct responses, green for deliberated

### Previous Release (v0.7.0)
- **System Date-Time MCP Server**: New MCP server for getting current system date and time
  - Tool: `get-system-date-time` with configurable return format
  - Formats: time only, date only, both, or Unix timestamp
  - Returns structured data with individual components

### Previous Release (v0.6.4)
- **Intelligent MCP Tool Calling**: Two-phase LLM-driven tool detection and execution
  - Phase 1: Analyzes queries against detailed MCP server capabilities
  - Phase 2: Generates specific tool calls with correct parameters
  - Comprehensive tool info for accurate selection

### Previous Release (v0.6.0)
- **MCP Integration**: Model Context Protocol for extensible tool capabilities
  - Calculator MCP server for basic math operations
  - Automatic tool detection based on query content
  - Tool usage displayed with server name, capability, input/output
  - Easy addition of new MCP servers via configuration

### Previous Release (v0.5.0)
- **Response Timing Display**: Real-time stopwatch showing thinking and total response time
  - Displays `<thinking_seconds>s/<total_seconds>s` format next to tokens/s
  - Orange-highlighted badge for easy visibility
  - Tracks thinking phase separately from response generation

### Previous Release (v0.4.0)
- **Quality-Based Multi-Round Deliberation**: Streaming multi-round with quality threshold
  - Each model rates (1-5) AND ranks peer responses with brief feedback
  - If any response rated <30%, triggers refinement round
  - Low-rated responses are refined based on peer feedback
  - Continues until quality threshold met or max_rounds reached
- **Tokens/Second Display**: Real-time tok/s metrics during streaming
  - Shows in tab headers and model labels
  - Updates live as tokens stream
- **Round Progress Indicator**: "Round X / Y" in Stage 2 header
  - Shows "(Refinement)" label for refinement rounds

### Previous Release (v0.3.4)
- **Metrics Markdown**: Auto-generated `data/llm_metrics.md` with model rankings and scores

### Previous Release (v0.3.3)
- **Markdown Export**: Final council answer automatically saved as markdown file
  - Format: `<title>__YYYY-MM-DD_HH-MM-SS.md` in project root

### Previous Release (v0.3.1)
- **Auto Retry**: Council members retry up to 2 times on blank/failed responses
- **Model Quality Metrics**: Automatic evaluation of responses to track model performance
  - Metrics: verbosity, expertise, adherence, clarity, overall rating
  - API: `/api/metrics` and `/api/metrics/ranking`

### Previous Release (v0.3.0)
- **Rich Formatted Output**: Presenter generates tables, headers, code blocks, and structured markdown
- **Redo Message**: Re-run the council process with the same question (↻ icon)
- **Edit Message**: Modify and resubmit any user message (✎ icon)

### Previous Release (v0.2.0)
- **Follow-up Questions**: Input field appears after Final Council Answer for multi-turn conversations
- **Formatter Model**: Optional separate LLM for formatting final answers (configurable, defaults to chairman)

### Previous Release (v0.1.0)
- **Token-Level Streaming**: Real-time display of LLM responses as they generate
- **Thinking Model Display**: Expandable sections showing reasoning model thought processes
- **Reactive Responses**: Concise prompts and configurable max_tokens for faster generation
- **Title Tooltips**: Full conversation title on hover for truncated sidebar items

### Stable Features
- **Multi-Round Deliberation**: Configurable rounds of iterative review and refinement
- **Background Title Generation**: Automatic meaningful titles for conversations with immediate generation for active sessions
- **Conversation Management**: Recycle bin system for safe conversation deletion and recovery
- **Smart Interface**: ID-based conversation labeling and intelligent button state management
- **Dynamic Configuration**: Change models and settings without code modifications
- **Local Privacy**: All processing happens locally via LM Studio - no data sent to external services

### Next Release
_See TODO.md for planned features_

### Future Roadmap
- **Model Quality Rating & Voting**: Council members rate and vote on each other's responses
- **Auto-Model Selection**: Dynamic model selection based on historical performance
- **Council Member Personalities**: Distinct personas for diverse perspectives
- **Advanced Deliberation Strategies**: Debate formats, consensus building
- **Model Performance Analytics**: Track individual model performance
- **Custom Prompt Templates**: Specialized prompts for different domains
- **Export & Sharing**: Export conversations in various formats
- **Integration Plugins**: Connect with external tools and knowledge bases

## Recent Changes

- ✅ **Token Streaming & Reactive Responses (v0.1.0)**: Real-time token streaming to UI, thinking model display, concise prompts
- ✅ **Enhanced Title Generation & Timeout Handling (v0.0.3)**: Sequential title generation, proper retry logic, circuit breaker pattern, and configurable timeouts for better reliability
- ✅ **Per-Model Connection Configuration**: Individual connection settings (IP, port, API base URL, API keys) for each model, enabling mixed deployment scenarios
- ✅ **Enhanced Model Validation**: Validates each model against its configured endpoint with detailed error reporting
- ✅ **Background Title Generation**: Automatic meaningful conversation titles with real-time UI updates
- ✅ **Multi-Round Deliberation**: Configurable deliberation rounds with cross-review and refinement
- ✅ **Conversation Management**: Soft delete (recycle bin), restore, and permanent deletion with improved UI/UX
- ✅ **Dynamic Configuration**: Runtime model and server configuration without code changes

## Vibe Code Alert

This project was 99% vibe coded as a fun Saturday hack because I wanted to explore and evaluate a number of LLMs side by side in the process of [reading books together with LLMs](https://x.com/karpathy/status/1990577951671509438). It's nice and useful to see multiple responses side by side, and also the cross-opinions of all LLMs on each other's outputs. I'm not going to support it in any way, it's provided here as is for other people's inspiration and I don't intend to improve it. Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like.

## Setup

### 0. Development Environment Setup

After cloning the repository, run the setup script to install git hooks:
```bash
./setup-dev.sh
```

This installs a pre-commit hook that prevents direct commits to master, enforcing the versioning workflow.

### 1. Install Dependencies

The project uses [uv](https://docs.astral.sh/uv/) for project management.

**Backend:**
```bash
uv sync
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

### 2. Setup LM Studio

**Install and configure LM Studio:**

1. Download and install [LM Studio](https://lmstudio.ai/), [Ollama](https://ollama.com/), or similar local inference server
2. Download the following models (note: these work well but may not be the best available - see [Planned Improvements](#planned-improvements) section):
   - `microsoft/phi-4-mini-reasoning`
   - `apollo-v0.1-4b-thinking-qx86x-hi-mlx`
   - `ai21-jamba-reasoning-3b-hi-mlx`
   - `qwen/qwen3-4b-thinking-2507`
3. Start your inference server (IP will be auto-detected or use localhost as fallback)
4. Load all models in your inference server

### 3. Configure Server & Models

The application automatically detects your local IP and validates model availability. Server and model settings are configured via `config.json` in the project root.

**Server Configuration:**
```json
{
  "server": {
    "ip": "",
    "port": "11434", 
    "base_url_template": "http://{ip}:{port}/v1",
    "api_key": ""
  }
}
```

- `ip`: Leave empty for auto-detection, or specify a custom IP address
- `port`: LM Studio server port (default: 11434)
- `base_url_template`: URL template for API endpoints
- `api_key`: Global API key (if required by your LLM server)

**Model Configuration:**

```json
{
  "models": {
    "council": [
      {
        "id": "microsoft/phi-4-mini-reasoning",
        "name": "Phi-4 Mini Reasoning",
        "description": "Microsoft's reasoning-optimized model",
        "ip": "",
        "port": "",
        "base_url_template": "",
        "api_key": ""
      },
      {
        "id": "apollo-v0.1-4b-thinking-qx86x-hi-mlx",
        "name": "Apollo 4B Thinking", 
        "description": "Apollo's thinking model with MLX optimization",
        "ip": "",
        "port": "",
        "base_url_template": "",
        "api_key": ""
      },
      {
        "id": "ai21-jamba-reasoning-3b-hi-mlx",
        "name": "AI21 Jamba Reasoning",
        "description": "AI21's Jamba reasoning model",
        "ip": "",
        "port": "",
        "base_url_template": "",
        "api_key": ""
      }
    ],
    "chairman": {
      "id": "qwen/qwen3-4b-thinking-2507",
      "name": "Qwen3-4B Thinking",
      "description": "Qwen's 4B thinking model for synthesis",
      "ip": "",
      "port": "",
      "base_url_template": "",
      "api_key": ""
    },
    "prompt_engineer": {
      "id": "",
      "name": "Prompt Engineer",
      "description": "Dynamic prompt generation (empty = use chairman)",
      "ip": "",
      "port": "",
      "base_url_template": "",
      "api_key": ""
    }
  },
  "deliberation": {
    "rounds": 2,
    "max_rounds": 5,
    "enable_cross_review": true,
    "refinement_prompt_template": "default"
  },
  "title_generation": {
    "enabled": true,
    "max_concurrent": 2,
    "timeout_seconds": 60,
    "retry_attempts": 3,
    "thinking_models": ["thinking", "reasoning", "o1"],
    "auto_expand_thinking": true
  }
}
```

**Per-Model Connection Parameters:**

Each model supports individual connection settings that override server defaults:

- **ip, port, base_url_template, api_key**: Model-specific connection parameters
- **Empty values**: Inherit from server configuration
- **Use case examples**:
  - Different models hosted on different servers
  - Some models requiring authentication, others not
  - Mixed deployment (local + remote models)

**Example Mixed Configuration:**
```json
{
  "server": {
    "ip": "192.168.1.111", 
    "port": "11434",
    "base_url_template": "http://{ip}:{port}/v1",
    "api_key": ""
  },
  "models": {
    "chairman": {
      "id": "qwen/qwen3-4b-thinking-2507",
      "ip": "192.168.1.100",
      "port": "8080",
      "base_url_template": "http://{ip}:{port}/api/v1", 
      "api_key": "special-key"
    }
  }
}
```

**Deliberation Settings:**
- `rounds`: Number of deliberation rounds (1-5, default: 2 for multi-round)
- `max_rounds`: Maximum allowed rounds 
- `enable_cross_review`: Enable response refinement based on peer feedback
- `refinement_prompt_template`: Template for refinement prompts

**Title Generation Settings:**
- `enabled`: Enable/disable background title generation (default: true)
- `max_concurrent`: Maximum concurrent title generations (default: 2)
- `timeout_seconds`: Timeout per title generation (default: 60)
- `retry_attempts`: Number of retry attempts for failed generations (default: 3)
- `thinking_models`: Keywords to identify thinking models (default: ["thinking", "reasoning", "o1"])
- `auto_expand_thinking`: Auto-expand thinking sections in UI (default: true)

**Timeout Configuration (v0.0.3+):**
- `default_timeout`: Default request timeout in seconds (default: 30)
- `title_generation_timeout`: Extended timeout for title generation (default: 60)
- `max_retries`: Maximum retry attempts for failed requests (default: 3)
- `retry_backoff_factor`: Exponential backoff multiplier for retries (default: 2)
- `circuit_breaker_threshold`: Failure count to trigger circuit breaker (default: 5)
- `connection_timeout`: Connection establishment timeout (default: 10)

```json
{
  "timeout_config": {
    "default_timeout": 30,
    "title_generation_timeout": 60,
    "max_retries": 3,
    "retry_backoff_factor": 2,
    "circuit_breaker_threshold": 5,
    "connection_timeout": 10
  }
}
```

### 3.1. Model Validation & Connectivity

The application automatically validates your LLM server setup on startup:

**Automatic Validation:**
- **IP Detection**: Auto-detects your local IP address for LM Studio connection
- **Connectivity Test**: Verifies connection to LM Studio server
- **Model Verification**: Ensures all configured models are loaded and available
- **Fallback Support**: Tries localhost (127.0.0.1) if auto-detected IP fails

**Error Handling:**
- **Clear Messages**: Detailed error descriptions for troubleshooting
- **Graceful Failure**: App won't start with invalid configuration
- **Troubleshooting Tips**: Helpful guidance for common setup issues

### 3.2. Enhanced Title Generation & Reliability (v0.0.3)

**Sequential Processing:**
- **Title First**: Title generation now runs before council deliberation to prevent server overload
- **Blocking Design**: Council members wait for title completion, ensuring resources aren't overwhelmed
- **Immediate Feedback**: Users see title generation progress in real-time

**Advanced Error Handling:**
- **Timeout Management**: Configurable timeouts for different request types (connection, read, title generation)
- **Retry Logic**: Exponential backoff with configurable retry attempts and delay factors
- **Circuit Breaker**: Automatic protection against unresponsive models with failure thresholds
- **Graceful Degradation**: Falls back to default titles when generation fails

**Real-time Processing:**
- **Progress Updates**: Live status updates during title generation ("generating", "thinking", "complete")
- **WebSocket Streaming**: Real-time communication for immediate UI feedback
- **Error Recovery**: Transparent retry attempts with user-visible progress
- **Thinking Model Support**: Special handling for reasoning models with expandable thought processes

**Configuration:**
```json
{
  "timeout_config": {
    "title_generation_timeout": 60,    // Extended timeout for complex title generation
    "max_retries": 3,                  // Number of retry attempts
    "retry_backoff_factor": 2,         // Exponential backoff (1s, 2s, 4s)
    "circuit_breaker_threshold": 5     // Failures before circuit opens
  }
}
```

You can edit `config.json` to customize the council lineup and deliberation behavior without changing code. The backend will automatically load the new configuration on restart.

**Validation**: Run `uv run python validate_models.py` to validate your configuration.

### 4. Conversation Management

The application includes a sophisticated conversation management system:

**Recycle Bin System:**
- **Safe Deletion**: Click the ✖️ icon next to any conversation to move it to the recycle bin
- **Visual Feedback**: Delete button changes from grey ✖️ to red ❌ on hover for clear action indication
- **Recovery Options**: Access deleted conversations via the 🗑️ Recycle Bin in the sidebar
- **Restore Functionality**: Use the ⟲ button to restore conversations from the recycle bin
- **Count Display**: Recycle bin shows the number of deleted conversations with a bold counter
- **Dual View Mode**: Switch between active conversations and recycle bin with a green ← back arrow

**Features:**
- **Soft Delete**: Conversations are safely moved to recycle bin rather than permanently deleted
- **Active Selection Management**: If you delete the currently active conversation, the view automatically clears
- **Automatic Refresh**: Conversation lists update automatically when items are deleted or restored
- **Clean Interface**: Deleted conversations don't clutter the main conversation list

### 5. Smart Conversation Management

The application includes intelligent conversation labeling and interface management:

**ID-Based Labeling:**
- **Unique Identification**: Conversations automatically labeled "Conversation [8-char-id]" format
- **Clear Distinction**: Easy to identify and navigate between different conversations
- **Automatic Migration**: Existing conversations updated from generic "New Conversation"
- **Future Compatible**: Title service can override with meaningful titles

**Smart Button States:**
- **Intelligent Enabling**: New Conversation button disabled when current conversation is empty
- **Visual Feedback**: Button turns grey (#cccccc) when disabled to prevent confusion
- **Interaction Prevention**: No hover effects or click handling when inappropriate
- **State Synchronization**: Updates automatically based on conversation content

**User Experience Benefits:**
- **Reduced Clutter**: Prevents creation of multiple empty conversations
- **Clear Navigation**: Easy identification of conversations through unique IDs
- **Intuitive Interface**: Button behavior matches user expectations and workflow

## Running the Application

The application includes automatic model validation and connectivity testing on startup.

**Option 1: Use the start script**
```bash
./start.sh
```

**What happens on startup:**
1. **Connectivity Test**: Auto-detects your local IP and tests connection to LM Studio
2. **Model Validation**: Verifies all configured models are loaded and available
3. **Error Prevention**: Won't start if models are missing or server unreachable
4. **Clear Feedback**: Detailed status messages and troubleshooting guidance

**Troubleshooting startup issues:**
- Ensure LM Studio is running with server enabled
- Verify all required models are loaded in LM Studio
- Check that model IDs in config.json match exactly (case-sensitive)
- Confirm network connectivity between application and LM Studio

**Option 2: Run manually**

Terminal 1 (Backend):
```bash
uv run python -m backend.main
```

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

## Recent Updates

### Conversation Sorting (v2.4.0)
- **Enhanced UX:** Conversations now display in chronological order (newest first) for improved accessibility
- **Backend Sorting:** Conversations sorted by creation timestamp at the storage layer
- **Frontend Optimization:** UI preserves server-side ordering for consistent user experience
- **Real-time Updates:** New conversations appear at the top of the list immediately

## API Testing

The backend exposes REST endpoints for testing and debugging functionality.

### MCP Server Status

Get all available MCP servers and their capabilities:

```bash
curl http://localhost:8001/api/mcp/status | jq
```

**Response includes:**
- `initialized`: Whether MCP registry is ready
- `servers`: List of registered MCP servers with their tools
- `total_tools`: Count of available tools

**Example response:**
```json
{
  "initialized": true,
  "servers": [
    {
      "name": "calculator",
      "tools": ["add", "subtract", "multiply", "divide"]
    },
    {
      "name": "system-datetime",
      "tools": ["get-system-date-time"]
    }
  ],
  "total_tools": 5
}
```

### Call MCP Tool Directly

```bash
curl -X POST "http://localhost:8001/api/mcp/call?tool_name=add&arguments={\"a\":5,\"b\":3}"
```

### Model Quality Metrics

Get all model performance metrics:
```bash
curl http://localhost:8001/api/metrics | jq
```

Get ranked model list:
```bash
curl http://localhost:8001/api/metrics/ranking | jq
```

## Automated Testing

The project includes a flexible automated testing framework for validating functionality.

### Running Tests

The test runner automatically starts and stops the server. No manual server management needed.

```bash
# Run all tests (auto-manages server)
uv run -m tests.test_runner

# Run specific scenario
uv run -m tests.test_runner --scenario current_news_websearch

# Filter by tags
uv run -m tests.test_runner --tags mcp,websearch

# Run with fix iterations (for CI/CD)
uv run -m tests.test_runner --max-iterations 3

# Use custom scenarios file
uv run -m tests.test_runner --scenarios-file tests/scenarios.json

# Disable auto-server (use existing running server)
uv run -m tests.test_runner --no-auto-server
```

### Test Scenarios

Tests are defined in `tests/scenarios.json` with the following structure:

```json
{
  "name": "current_news_websearch",
  "query": "What are today's top 5 news headlines?",
  "expected_behavior": {
    "tool_used": "websearch.search",
    "no_refusal": true,
    "has_content": true,
    "min_length": 100
  },
  "tags": ["mcp", "websearch", "current-events"]
}
```

**Expected Behavior Checks:**
- `tool_used`: Verify specific MCP tool was invoked
- `response_type`: Check if `direct` or `deliberation`
- `contains`: List of substrings that must appear in response
- `not_contains`: List of forbidden substrings
- `no_refusal`: Ensure no "I cannot access" style refusals
- `has_content`: Check minimum response length
- `min_length`: Specific character minimum

### Test Results

Results are saved to `tmp/test_results/` with timestamps. Each run generates:
- JSON file with detailed results per test
- Console report with pass/fail summary
- Diagnostic info for debugging failures

### Adding Custom Tests

1. Edit `tests/scenarios.json` to add scenarios
2. Use tags to organize tests by feature area
3. Run with `--tags your-tag` to test specific areas

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), async httpx, LM Studio API, multi-round deliberation, background title generation, conversation management, dynamic configuration
- **Frontend:** React + Vite, react-markdown for rendering
- **Storage:** JSON files in `data/conversations/`
- **Package Management:** uv for Python, npm for JavaScript
- **AI Infrastructure:** LM Studio for local model hosting
