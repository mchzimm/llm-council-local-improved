# Changelog

Completed changes with version, branch, and timestamp information.

## Completed Changes

### v0.22.4
**Branch:** `v0.22.4`  
**Completed:** 2025-11-29 06:10 UTC | 2025-11-28 22:10 PST

**Fixes:**
- **Hide Duplicates from Main List**: Duplicate conversations are now only shown in the collapsible Duplicates section
  - Main conversation list filters out duplicate IDs
  - Uses `filteredConversations` computed from `duplicateInfo`
  - Keeps first/newest conversation in main list, shows rest in Duplicates section

**Changes:**
- `frontend/src/components/Sidebar.jsx` - Filter duplicates from main list

---

### v0.22.3
**Branch:** `v0.22.3`  
**Completed:** 2025-11-29 06:05 UTC | 2025-11-28 22:05 PST

**Fixes:**
- **Title Generation for Default Titles**: Fixed title generation not working at startup
  - `_needs_title_generation()` now works with metadata-only conversation dicts
  - Handles both `messages` array and `message_count` property
  - Excludes deleted conversations from title generation
  - Excludes duplicate conversations from title generation queue

**Features:**
- **Duplicates Collapsible Section**: Added collapsible section showing duplicate conversations
  - Purple collapsible section above "Clean Duplicates" button
  - Shows duplicate groups with first query preview
  - Click to navigate to any duplicate conversation
  - Collapsed by default

**Changes:**
- `backend/title_service.py` - Fixed `_needs_title_generation()`, exclude duplicates
- `frontend/src/components/Sidebar.jsx` - Added duplicates section
- `frontend/src/components/Sidebar.css` - Added duplicates styling

---

### v0.22.2
**Branch:** `v0.22.2`  
**Completed:** 2025-11-29 05:58 UTC | 2025-11-28 21:58 PST

**Fixes:**
- **Duplicate Cleanup Fix**: Fixed `soft_delete_conversation is not defined` error
  - Added `soft_delete_conversation()` function to `storage.py`
  - Function marks conversation as deleted with timestamp
  - Used by `delete_duplicate_conversations()` for soft deletion

**Changes:**
- `backend/storage.py` - Added `soft_delete_conversation()` function

---

### v0.22.0
**Branch:** `v0.22.0`  
**Completed:** 2025-11-29 05:50 UTC | 2025-11-28 21:50 PST

**Features:**
- **Duplicate Conversation Cleanup**: UI to find and delete duplicate conversations
  - New backend endpoints:
    - `GET /api/conversations/duplicates` - Find duplicate conversation groups
    - `POST /api/conversations/duplicates/delete` - Delete duplicates, keep newest
  - Sidebar "Clean Duplicates" button (appears when duplicates exist)
  - Shows count of removable duplicates
  - Confirms before deletion, keeps newest copy of each group

**Technical Details:**
- `find_duplicate_conversations()` - Groups conversations by MD5 hash of user queries
- `delete_duplicate_conversations()` - Soft-deletes duplicates, keeps one per group
- Frontend fetches duplicate info on mount and when conversations change

**Changes:**
- `backend/storage.py` - Added duplicate detection and deletion functions
- `backend/main.py` - Added API endpoints for duplicates
- `frontend/src/components/Sidebar.jsx` - Added cleanup button and logic
- `frontend/src/components/Sidebar.css` - Added button styling

---

### v0.21.3
**Branch:** `v0.21.3`  
**Completed:** 2025-11-29 05:45 UTC | 2025-11-28 21:45 PST

**Fixes:**
- **Title Generation at Startup**: Fixed conversations with default titles ("Conversation <id>") not being regenerated
  - Added `initialize_title_service()` call during app startup
  - Title service now scans for untitled conversations and queues them for generation
  - Added `shutdown_title_service()` call during app shutdown for clean cleanup
  - Import both `title_service` functions and instance from separate modules

**Technical Details:**
- `title_service.py` contains the full TitleGenerationService with background worker
- `title_generation.py` contains the simpler TitleGenerationService instance
- Both are now properly imported and used in main.py

**Changes:**
- `backend/main.py` - Initialize title service at startup, shutdown at exit

---

### v0.21.2
**Branch:** `v0.21.2`  
**Completed:** 2025-11-29 03:35 UTC | 2025-11-28 19:35 PST

**Fixes:**
- **Calculator Tool Routing**: Fixed "5 plus 3" not using calculator MCP tool
  - Added deterministic `_parse_calculator_query()` function for reliable number extraction
  - Maps data type "calculation" to just "calculator" server (not specific operation)
  - Phase 2 now uses fast path for calculator with regex-based number parsing
  - Supports: plus/add, minus/subtract, times/multiply, divided/divide operations
  - Avoids LLM unreliability in parsing simple numbers

- **Math Query Detection Override**: Added post-processing fix for expectation analysis
  - LLM sometimes says simple math doesn't need tools (treating it as "general knowledge")
  - Added deterministic override that forces `needs_external_data: true` for any query with numbers and math keywords
  - Keywords: plus, minus, times, divided, multiply, add, subtract, calculate, compute, +, -, *, /, etc.

**Technical Details:**
- Tool execution works correctly (verified: a=5, b=3 → result=8)
- Response generation sometimes hallucinates wrong numbers (LLM issue, not tool issue)
- Test updated: `calculator_addition` with query "What is 5 plus 3?"

**Changes:**
- `backend/council.py` - Added `_parse_calculator_query()`, math detection override
- `tests/scenarios.json` - Updated calculator_addition test, fixed factual_capital min_length

---

### v0.21.1
**Branch:** `v0.21.1`  
**Completed:** 2025-11-29 03:10 UTC | 2025-11-28 19:10 PST

**Documentation:**
- **README.md Update**: Added v0.21.0 feature documentation (was missing)
  - Added "Current Release (v0.21.0)" section for LLM-Based Tool Confidence Routing
  - Moved previous v0.20.0 to "Previous Release" section

- **AGENTS.md Improvements**: Made README updates more prominent to prevent future misses
  - Added warning symbols and "DO NOT SKIP" emphasis
  - Added README Update Checklist before commit
  - Added Step 5 "Update Documentation" in Versioning Process (before commit step)
  - Made README update a mandatory step with verification checklist

**Changes:**
- `README.md` - Added v0.21.0 feature documentation
- `AGENTS.md` - Enhanced README update instructions

---

### v0.21.0
**Branch:** `v0.21.0`  
**Completed:** 2025-11-29 03:00 UTC | 2025-11-28 19:00 PST

**Features:**
- **LLM-Based Tool Confidence Routing**: Replaced hardcoded keyword lists with intelligent LLM-based system
  - Step 1: LLM analyzes user expectations and determines data types needed
  - Step 2: Deterministic mapping from data types to appropriate tools
  - More flexible and extensible than keyword matching

**Architecture:**
- New `_analyze_user_expectations()`: LLM call to extract user expectations and data type needs
- New `_evaluate_tool_confidence()`: Fast deterministic data-type-to-tool mapping
- Removed: `WEBSEARCH_KEYWORDS`, `GEOLOCATION_KEYWORDS`, `_requires_websearch()`, `_requires_geolocation()`
- Added: `TOOL_CONFIDENCE_THRESHOLD` (0.5) for tool selection

**Data Type Mappings:**
- `current_time` → system-date-time.get-system-date-time (95% confidence)
- `location` → system-geo-location.get-system-geo-location (95% confidence)
- `news`, `weather`, `current_events` → websearch.search (90% confidence)
- `calculation` → calculator tools (85% confidence)
- `web_content` → retrieve-web-page.get-page-from-url (80% confidence)

**Benefits:**
- Single LLM call for expectation analysis (vs two LLM calls in pure LLM approach)
- Fast, deterministic tool selection based on data types
- More maintainable than keyword lists
- Extensible - add new data types and tools easily

**Test Results:** All 6 test scenarios pass (100%)

**Changes:**
- `backend/council.py` - New expectation-based tool routing system
- `backend/main.py` - Always run tool check (LLM handles no-tool cases)

---

### v0.20.4
**Branch:** `v0.20.4`  
**Completed:** 2025-11-29 02:45 UTC | 2025-11-28 18:45 PST

**Fixes:**
- **Geolocation Tool Fast-Path**: Added keyword-based fast-path for geolocation queries
  - "What's my address?" now correctly triggers the geo-location tool
  - Added `GEOLOCATION_KEYWORDS` list similar to `WEBSEARCH_KEYWORDS`
  - Added `_requires_geolocation()` function for keyword detection
  - Updated `_phase1_analyze_query()` with geolocation fast-path
  - Updated `needs_tool_check` condition in main.py

**Keywords Added:**
- `my location`, `my address`, `where am i`, `what's my address`
- `my ip`, `my city`, `my country`, `located`, `my postal`
- `my zip code`, `my region`, `geolocation`, `ip address`
- `what city`, `which city`, `what state`, `which state`
- `what country`, `which country`

**Additional:**
- Added refusal phrases for "don't have access to personal"
- Enabled geolocation test scenario in scenarios.json

**Changes:**
- `backend/council.py` - Added GEOLOCATION_KEYWORDS and _requires_geolocation()
- `backend/main.py` - Added geolocation check to needs_tool_check condition
- `tests/scenarios.json` - Updated geolocation test scenario

---

### v0.20.3
**Branch:** `v0.20.3`  
**Completed:** 2025-11-29 01:45 UTC | 2025-11-28 17:45 PST

**Improvements:**
- **Graphiti Edge Extraction Logging**: Reduced log noise for missing entity warnings
  - Changed log level from WARNING to DEBUG for "Invalid entity IDs in edge extraction"
  - Added new `patch_edge_logging.py` patch script
  - Updated Dockerfile to apply patch during build
  - Edges with missing entities still skipped, but logs are cleaner

**Technical Details:**
- The issue occurs when LLM edge extraction references entities not in the entity list
- This is expected behavior with local LLMs due to inconsistent entity/edge extraction
- Full multi-turn extraction would require significant upstream changes
- Current solution: Clean logs + skip invalid edges (same behavior, less noise)

**Changes:**
- `mcp_servers/graphiti-custom/patch_edge_logging.py` - New patch script
- `mcp_servers/graphiti-custom/Dockerfile` - Added patch execution
- `mcp_servers/graphiti-custom/README.md` - Updated documentation

---

### v0.20.2
**Branch:** `v0.20.2`  
**Completed:** 2025-11-29 01:25 UTC | 2025-11-28 17:25 PST

**Documentation:**
- **Graphiti Edge Extraction Warning**: Documented upstream graphiti_core warning
  - "Invalid entity IDs in edge extraction" is gracefully handled (edge skipped)
  - Caused by LLM inconsistency in entity vs edge extraction
  - No fix needed - this is expected behavior with local LLMs
  - Updated `mcp_servers/graphiti-custom/README.md` with Known Warnings section

**Changes:**
- `mcp_servers/graphiti-custom/README.md` - Added Known Warnings documentation

---

### v0.20.1
**Branch:** `v0.20.1`  
**Completed:** 2025-11-29 01:05 UTC | 2025-11-28 17:05 PST

**Features:**
- **Graphiti Test Runner Script**: New `run_graphiti_test.sh` for running Graphiti tests
  - Automatically starts/restarts Graphiti MCP server with latest config
  - Waits for server health before running tests
  - Reports test results with helpful diagnostics

**Fixes:**
- **Separate Test Database**: Graphiti tests now use `test_graphiti` group_id
  - Prevents test data from conflicting with production LLM Council data
  - LLM Council uses `llm_council` group_id, tests use `test_graphiti`

- **Test Scenarios Updated**: Enabled more test scenarios and fixed assertions
  - `current_news_websearch` - Verified working
  - `current_date_tool` - Verified working  
  - `factual_capital` - Fixed min_length assertion
  - `chat_greeting` - Verified working
  - `real_time_data_awareness` - Verified working

**Changes:**
- `run_graphiti_test.sh` - New test runner script
- `tests/test_graphiti.py` - Changed group_id to `test_graphiti`
- `tests/scenarios.json` - Enabled core tests, fixed assertions

---

### v0.20.0
**Branch:** `v0.20.0`  
**Completed:** 2025-11-29 00:45 UTC | 2025-11-28 16:45 PST

**Features:**
- **Graphiti Memory Integration**: Persistent memory with confidence-based fast-path responses
  - New `backend/memory_service.py` module for Graphiti knowledge graph interaction
  - Records all messages (user, council members, chairman) to memory asynchronously
  - Memory-based response path when confidence exceeds threshold (default 80%)
  - Configurable confidence model in `config.json` (defaults to chairman if not specified)
  - Age-weighted confidence scoring for memory freshness (max_memory_age_days configurable)
  - Graceful degradation when Graphiti unavailable - standard workflow continues
  - New `/api/memory/status` endpoint for memory service status

**Changes:**
- `backend/memory_service.py` - New memory service module with MemoryService class
- `backend/main.py` - Added memory initialization, check, and recording hooks
- `backend/config_loader.py` - Added `get_memory_config()` and `get_confidence_model()`
- `config.json` - Added `memory` section and `confidence` model configuration
- `README.md` - Updated Key Features section with v0.20.0 release info
- `openspec/changes/add-graphiti-memory-integration/` - Change proposal

**Configuration:**
```json
{
  "models": {
    "confidence": {
      "id": "",
      "name": "Memory Confidence Scorer",
      "description": "Model for scoring memory relevance (empty = use chairman)"
    }
  },
  "memory": {
    "enabled": true,
    "confidence_threshold": 0.8,
    "max_memory_age_days": 30,
    "group_id": "llm_council",
    "record_user_messages": true,
    "record_council_responses": true,
    "record_chairman_synthesis": true
  }
}
```

---

### v0.19.2
**Branch:** `v0.19.2`  
**Completed:** 2025-11-29 00:05 UTC | 2025-11-28 16:05 PST

**Fixes:**
- **Enforce Project tmp/ Folder Usage**: Added explicit rule in AGENTS.md to always use project's `tmp/` folder
  - Never use system `/tmp/` directory
  - Documents correct paths: `tmp/test_results/`, `tmp/intake.md`
  - Prevents temporary files from being created outside project

**Changes:**
- `AGENTS.md` - Added "Critical Rules" section with tmp folder guidance

---

### v0.19.1
**Branch:** `v0.19.1`  
**Completed:** 2025-11-28 23:54 UTC | 2025-11-28 15:54 PST

**Fixes:**
- **Prevent Direct Master Commits**: Added git pre-commit hook to enforce versioning workflow
  - Hook blocks commits to master/main with helpful error message
  - Warns when branch name doesn't follow `v<release>.<feature>.<fix>` format
  - New `setup-dev.sh` script installs hooks after cloning
  - Updated AGENTS.md with hook documentation
  - Updated README with setup instructions

**Changes:**
- `.git/hooks/pre-commit` - Git hook (local, installed via setup script)
- `setup-dev.sh` - Development environment setup script
- `AGENTS.md` - Added Git Hook Protection section
- `README.md` - Added Step 0 for dev environment setup

---

### v0.19.0
**Branch:** `v0.19.0`  
**Completed:** 2025-11-28 23:52 UTC | 2025-11-28 15:52 PST

**Features:**
- **JSON Configuration for Graphiti MCP**: Added centralized JSON-based configuration system
  - New `graphiti_config.json` as main config file for LLM, embedder, database settings
  - New `generate_config.py` script to generate `config.yaml` and `.env` from JSON
  - Updated `start.sh` to auto-regenerate config on startup
  - Updated README with full documentation and troubleshooting guide

**Changes:**
- `mcp_servers/graphiti-custom/graphiti_config.json` - Main configuration file
- `mcp_servers/graphiti-custom/generate_config.py` - Config generator script
- `mcp_servers/graphiti-custom/start.sh` - Updated to use JSON config
- `mcp_servers/graphiti-custom/README.md` - Full documentation update
- `mcp_servers/graphiti-custom/.gitignore` - Added .env

---

### v0.15.5
**Branch:** `v0.15.5`  
**Completed:** 2025-11-28 09:50 UTC | 2025-11-28 01:50 PST

**Fixes:**
- **Tool Failure Honest Reporting**: Fixed test validation and model behavior when MCP tools fail internally
  - Added `evaluate_tool_success()` to test framework - checks tool output content for success/error
  - Added `_tool_output_failed()` helper to detect tool failures from output JSON
  - Updated `format_tool_result_for_prompt()` to detect failures and instruct honest reporting
  - Updated prompts to tell models NOT to fabricate data when tools fail
  - Tests now correctly fail when tool returns error in output (previously passed incorrectly)
  - Models now honestly report "tool failed" instead of making up fake data

**Changes:**
- `backend/council.py` - Tool failure detection, honest failure prompts
- `tests/test_runner.py` - Tool success validation in test evaluator
- `openspec/changes/fix-tool-failure-honest-reporting.md` - OpenSpec proposal

---

### v0.15.4
**Branch:** `v0.15.4`  
**Completed:** 2025-11-28 09:25 UTC | 2025-11-28 01:25 PST

**Fixes:**
- **LLM Tool Awareness**: Fixed models refusing to use MCP tool data claiming "cannot access real-time information"
  - Strengthened system prompts with explicit instructions to use tool output as factual data
  - Added refusal phrase detection with automatic retry using stronger prompts
  - Enhanced tool result formatting with timestamps and "LIVE DATA" emphasis
  - Added weather-related keywords to websearch trigger list
  - Fixes: Models now correctly use websearch/tool results instead of claiming training data limitations

**Changes:**
- `backend/council.py` - Refusal detection, retry logic, stronger prompts, enhanced tool formatting
- `openspec/changes/fix-llm-tool-awareness/` - OpenSpec proposal documentation

---

### v0.15.3
**Branch:** `v0.15.3`  
**Completed:** 2025-11-28 08:45 UTC | 2025-11-28 00:45 PST

**Fixes:**
- **Non-streaming API Routing**: Added intelligent message classification and routing to non-streaming endpoint
  - `/api/conversations/{id}/message` now classifies messages before processing
  - Simple/factual queries route to direct response (skip council deliberation)
  - Tool usage works for both direct and deliberation response paths
  - Significantly faster responses for factual questions and chat
  - Fixes: test framework timeout issues, real-time data queries now work in non-streaming API

**Changes:**
- `backend/main.py` - Complete rewrite of send_message endpoint with classification and routing
- `tests/test_runner.py` - Updated to properly handle direct_response in result
- `tests/scenarios.json` - Added 'core' tag for critical tests, adjusted timeouts
- `openspec/AGENTS.md` - Added auto-implementation instructions after proposal validation

---

### v0.15.1
**Branch:** `v0.15.1`  
**Completed:** 2025-11-28 07:15 UTC | 2025-11-27 23:15 PST

**Fixes:**
- **Message Re-run Cleanup**: Fixed duplicate messages appearing when re-running a conversation
  - Added `truncate_at` and `skip_user_message` params to API
  - Backend truncates messages at specified index before re-run
  - Frontend passes truncateAt for redo/edit message operations
  - Fixes: re-running messages no longer leaves stale responses
  
- **Websearch URL Format**: Fixed SearXNG search endpoint compatibility
  - Changed URL from `?q="{query}"` to `/search?q={query}` format
  - Spaces now replaced with `+` instead of URL encoding
  - Added HTML result parsing (extracts title, URL, snippet from SearXNG response)
  - Fixes: websearch MCP tool now returns proper search results

**Files Changed:**
- `backend/main.py` - Added truncate_at/skip_user_message to SendMessageRequest
- `frontend/src/App.jsx` - Pass truncateAt to API for redo/edit
- `frontend/src/api.js` - Added truncateAt, skipUserMessage params
- `mcp_servers/websearch/server.py` - Fixed URL format, added HTML parsing

---

### v0.8.5
**Branch:** `v0.8.5-test-infrastructure`  
**Completed:** 2025-11-28 07:00 UTC | 2025-11-27 23:00 PST

**Fixes:**
- **Title Service Method Error**: Fixed 500 Internal Server Error when sending first message
  - Removed undefined `get_title_service()` call - service is already imported
  - Fixed `generate_title_immediate` → `generate_title` method name
  - Fixes: send_message endpoint crashing on first conversation message

**Features:**
- **Automated Test Infrastructure**: Added comprehensive test framework
  - `tests/test_runner.py` - Full test runner with server lifecycle management
  - `tests/test_mcp_tools.py` - Quick MCP tool validation script
  - `tests/scenarios.json` - Configurable test scenarios
  - Auto-starts/stops server for automated testing
  - Support for MCP direct tool calls and full council tests

**Files Changed:**
- `backend/main.py` - Fixed title service method calls
- `tests/test_runner.py` - New automated test runner
- `tests/test_mcp_tools.py` - New MCP tool tests (8 tests, 100% pass rate)
- `tests/scenarios.json` - Test scenario definitions
- `tests/__init__.py` - Package marker

---

### v0.8.3
**Branch:** `v0.8.3`  
**Completed:** 2025-11-28 05:40 UTC | 2025-11-27 21:40 PST

**Fixes:**
- **MCP Websearch Not Triggered for News Queries**: Fixed tool detection for current events
  - Added keyword-based pre-detection (news, latest, trending, headlines, etc.)
  - Short-circuit to websearch.search when keywords detected
  - Strengthened Phase 1 analysis prompt with explicit tool routing rules
  - Clarified that model HAS access to external tools
  - Fixes: "what are today's top 5 news" now correctly uses websearch tool

**Files Changed:**
- `backend/council.py` - Added WEBSEARCH_KEYWORDS, _requires_websearch(), updated _phase1_analyze_query()

---

### v0.14.1
**Branch:** `v0.14.1`  
**Completed:** 2025-11-28 05:35 UTC | 2025-11-27 21:35 PST

**Fixes:**
- **TokenTracker Definition Order**: Fixed NameError preventing backend startup
  - TokenTracker class was used before its definition in council.py
  - Moved class definition from line 299 to immediately after imports (line 20)
  - Fixes: `NameError: name 'TokenTracker' is not defined`

**Files Changed:**
- `backend/council.py` - Moved TokenTracker class to top of file

---

### v0.14.0
**Branch:** `v0.14.0`  
**Completed:** 2025-11-28 05:21 UTC | 2025-11-27 21:21 PST

**Features:**
- **Formatter Model for Direct Responses**: Added two-step response generation for direct responses
  - Chairman model first generates the response content
  - Formatter model (if configured and different) improves formatting
  - New frontend event handlers for formatter streaming (formatter_start, formatter_token, formatter_thinking, formatter_complete)
  - Falls back to chairman model if formatter not configured or same as chairman
  - Config supports separate formatter model with full connection parameters

**Files Changed:**
- `backend/council.py` - Added `_apply_formatter()` function and formatter integration in `chairman_direct_response()`
- `frontend/src/App.jsx` - Added formatter event handlers in both WebSocket processing paths
- `config.json` - Set formatter model to qwen/qwen3-4b-thinking-2507

---

### v0.8.2
**Branch:** `v0.8.2`  
**Completed:** 2025-11-28 04:49 UTC | 2025-11-27 20:49 PST

**Fixes:**
- **Classification Status Display**: Fixed "Analyzing..." status persisting after response completes
  - Classification status now properly updates to 'complete' in direct_response_complete handler
  - Classification status now properly updates to 'complete' in stage3_complete handler
  - Both streaming path and standard path fixed

- **MCP Date Context**: Fixed MCP tools returning outdated dates (e.g., "July 2024")
  - Added current date/time context to tool analysis prompt in _phase1_analyze_query
  - Model now receives actual current date/time for time-sensitive tool decisions
  - Added time context to chairman_direct_response for consistent date awareness

**Files Changed:**
- `frontend/src/App.jsx` - Updated completion handlers
- `backend/council.py` - Added datetime import and time context

---

### v0.8.1
**Branch:** `v0.8.1`  
**Completed:** 2025-11-28 03:59 UTC | 2025-11-27 19:59 PST

**Fixes:**
- **Overlay Hover Behavior**: Fixed issue where overlays would close when cursor briefly moved over title area and back into overlay
  - Added unified hover tracking for title-area element
  - Both title-area and overlay containers now properly maintain hover state
  - Prevents accidental closure during normal mouse movement

**Changes:**
- Updated `handleTitleAreaEnter` to set both hover states
- Unified title-area hover tracking to prevent premature overlay closure

---

### v0.13.0
**Branch:** `v0.13.0`  
**Completed:** 2025-11-28 03:55 UTC | 2025-11-27 19:55 PST

**Features:**
- **Overlay Hover Delay**: 2-second delay before MCP overlays close
  - Allows smooth navigation between MCP server overlay and tools overlay
  - Timer cancels when cursor re-enters any overlay in the group
  - Both the server list and tools overlays are part of the same group

**Changes:**
- Added `overlayCloseTimerRef` for managing close delay
- Added `handleOverlayGroupEnter` and `handleOverlayGroupLeave` functions
- Applied overlay group handlers to title-area, mcp-overlay, and mcp-tools-overlay
- Removed immediate close on server item mouse leave

---

### v0.12.0
**Branch:** `v0.12.0`  
**Completed:** 2025-11-28 03:45 UTC | 2025-11-27 19:45 PST

**Features:**
- **MCP Status Indicator**: Visual MCP server status in sidebar header
  - "MCP" badge next to "LLM Council" title (blue bold with grey edge)
  - Hover overlay showing all MCP servers with status indicators
  - Red (offline), yellow (busy), green (available) status colors
  - Secondary hover overlay showing server tools
  - Tool in-use highlighting (yellow) for active tools
  - Metrics display: server count, tool count, active tools

**Changes:**
- Enhanced `backend/mcp/registry.py` with server/tool status tracking
- Added `getMcpStatus()` API function in `frontend/src/api.js`
- Updated `frontend/src/components/Sidebar.jsx` with MCP overlay UI
- Added 145+ lines of CSS for overlay styling

---

### v0.11.0
**Branch:** `change-022-system-timezone-mcp-server`  
**Completed:** 2025-11-28 02:55 UTC | 2025-11-27 18:55 PST

**Features:**
- **system-timezone-mcp**: New MCP server for retrieving timezone information
  - Tool: `get-timezone-list` with no input parameters
  - Returns: System timezone (based on IP) and complete list of tz database timezones
  - Parses Wikipedia's List of tz database time zones page
  - 24-hour caching for timezone list (data rarely changes)
  - Fallback to minimal timezone list if Wikipedia unavailable

**Changes:**
- Created `mcp_servers/system_timezone/` directory with server.py
- Added server to `mcp_servers.json` configuration
- Server uses http_wrapper for HTTP/stdio dual mode

---

### v0.10.0
**Branch:** `change-021-system-geo-location-mcp-server`  
**Completed:** 2025-11-28 01:40 UTC | 2025-11-27 17:40 PST

**Features:**
- **system-geo-location-mcp**: New MCP server for retrieving system location based on IP
  - Tool: `get-system-geo-location` with no input parameters
  - Returns: City, State/Region, Postal Code, Country
  - Uses whatismyip.com for IP-based geolocation
  - No external API keys required

**Changes:**
- Created `mcp_servers/system_geo_location/` directory with server.py
- Added server to `mcp_servers.json` configuration
- Server uses http_wrapper for HTTP/stdio dual mode

---

### v0.9.0
**Branch:** `change-020-retrieve-web-page-mcp-server`  
**Completed:** 2025-11-27 22:05 UTC | 2025-11-27 14:05 PST

**Features:**
- **retrieve-web-page-mcp**: New MCP server for fetching HTML content from URLs
  - Tool: `get-page-from-url` with URL input parameter
  - Returns success status, URL, content, and HTTP status code
  - Handles HTTP errors, URL errors, and timeouts (30s)
  - User-Agent: `Mozilla/5.0 (compatible; LLMCouncil/1.0)`
  - Foundation for geo-location and timezone MCP servers

**Changes:**
- Created `mcp_servers/retrieve_web_page/` directory with server.py
- Added server to `mcp_servers.json` configuration
- Server uses http_wrapper for HTTP/stdio dual mode

---

### v0.8.0
**Branch:** `v0.8.0`  
**Completed:** 2025-11-27 18:45 UTC | 2025-11-27 10:45 PST

**Features:**
- **intelligent-message-routing**: Chairman classifies messages before deliberation
  - Phase 0: Classification - chairman evaluates message type (factual/chat/deliberation)
  - Direct response path for factual questions and casual chat (skips council stages)
  - Full 3-stage deliberation for complex questions requiring opinions/comparison/feedback
  - Visual classification badges in UI showing response type
  - Blue-themed styling for direct responses vs green for deliberated answers

**Changes:**
- `backend/council.py`: Added `classify_message()` and `chairman_direct_response()` functions
- `backend/main.py`: Routing logic in streaming endpoint based on classification
- `frontend/src/App.jsx`: Event handlers for classification and direct response events
- `frontend/src/components/ChatInterface.jsx`: Conditional rendering based on response type
- `frontend/src/components/Stage3.jsx`: Support for `isDirect` prop with different styling
- `frontend/src/components/ChatInterface.css`: Classification badge styling
- `frontend/src/components/Stage3.css`: Direct response styling (blue theme)
- `openspec/changes/change-023-intelligent-message-routing.md`: Proposal document

---

### v0.7.0
**Branch:** `v0.7.0`  
**Completed:** 2025-11-27 17:29 UTC | 2025-11-27 09:29 PST

**Features:**
- **system-date-time-mcp**: New MCP server for getting system date and time
  - Tool: `get-system-date-time` with `return_type` parameter
  - Formats: `time` (HH:MM:SS), `date` (YYYY-MM-DD), `both` (full datetime), `unix` (timestamp)
  - Returns structured data with individual components (year, month, day, hour, minute, second, weekday, ISO format)

**Changes:**
- Created `mcp_servers/system_date_time/` directory with server.py
- Added server to `mcp_servers.json` configuration
- Server runs on dynamic port (base_port + index)

---

### v0.6.4
**Branch:** `v0.6.4`  
**Completed:** 2025-11-27 17:00 UTC | 2025-11-27 09:00 PST

**Features:**
- **intelligent-mcp-tool-calling**: Two-phase LLM-driven tool detection and execution
  - Phase 1: Analysis - tool_calling model analyzes queries against detailed MCP server info
  - Phase 2: Execution - generates specific tool calls with correct parameters
  - Comprehensive tool info includes server details, tool descriptions, parameters, types, and allowed values
  - Removes hardcoded keyword matching in favor of intelligent LLM analysis
  - Better tool selection accuracy for math, web search, and future MCP capabilities

**Changes:**
- `backend/council.py`: Refactored `check_and_execute_tools()` into two-phase approach
  - Added `_extract_json_from_response()` helper for robust JSON parsing
  - Added `_phase1_analyze_query()` for intelligent query analysis
  - Added `_phase2_generate_tool_call()` for tool call generation
- `backend/mcp/registry.py`: Added `get_detailed_tool_info()` for comprehensive tool documentation
  - Simplified `should_use_tools()` to defer to LLM analysis

---

### v0.6.3
**Branch:** `v0.6.3`  
**Completed:** 2025-11-27 16:30 UTC | 2025-11-27 08:30 PST

**Features:**
- **mcp-server-dynamic-ports**: HTTP transport for MCP servers
  - MCP servers now run on HTTP ports starting at 15000
  - Sequential port assignment: calculator=15000, websearch=15001, etc.
  - Added `/health` endpoint for server readiness checks
  - HTTP JSON-RPC replaces stdio communication
  - Enables better monitoring, debugging, and external tool integration

**Changes:**
- `mcp_servers.json`: Added `base_port` (15000) and optional `port` per server
- `mcp_servers/http_wrapper.py`: New HTTP server wrapper for MCP servers
- `mcp_servers/calculator/server.py`: Uses http_wrapper for HTTP/stdio dual mode
- `mcp_servers/websearch/server.py`: Uses http_wrapper for HTTP/stdio dual mode
- `backend/mcp/client.py`: Added HTTP transport support alongside stdio
- `backend/mcp/registry.py`: Dynamic port assignment and port tracking

---

### v0.6.2
**Branch:** `v0.6.2`  
**Completed:** 2025-11-27 12:15 UTC | 2025-11-27 04:15 PST

**Features:**
- **websearch-mcp**: Web search capability via MCP server
  - Local search endpoint integration at `http://127.0.0.1:8080?q="<search>"`
  - Automatic detection of time-sensitive topics, current events, specific entities
  - Search results formatted and injected into council context
  - Keywords: current, latest, news, price, weather, who is, etc.

**Changes:**
- Created `mcp_servers/websearch/` with server.py implementing MCP protocol
- Updated `mcp_servers.json` to include websearch server
- Updated `backend/mcp/registry.py` with search indicators in `should_use_tools()`

---

### v0.6.1
**Branch:** `v0.6.1`  
**Completed:** 2025-11-27 11:35 UTC | 2025-11-27 03:35 PST

**Features:**
- **tool-calling-model-config**: Dedicated tool_calling model configuration for MCP
  - Added `tool_calling` model section in config.json
  - Set `nexveridian/granite-4.0-h-tiny` as default tool-calling model
  - Separates MCP tool decisions from council reasoning models
  - Allows use of faster/smaller models optimized for function calling

**Changes:**
- `config.json`: Added tool_calling model configuration section
- `backend/config_loader.py`: Added `get_tool_calling_model()` function and model connection resolution
- `backend/council.py`: Updated to use tool_calling model for MCP tool decisions

---

### v0.6.0
**Branch:** `v0.6.0`  
**Completed:** 2025-01-27 10:20 UTC | 2025-01-27 02:20 PST

**Features:**
- **mcp-capability**: Model Context Protocol (MCP) integration for extensible tool usage
  - MCP client/registry for discovering and managing MCP servers
  - Calculator MCP server for basic math operations (add, subtract, multiply, divide)
  - Automatic tool detection based on query content
  - Tool usage displayed with server name, capability, input/output in Stage 1
  - Purple-themed tool result card in UI

**Changes:**
- Created `backend/mcp/` module with client.py and registry.py
- Created `mcp_servers/calculator/` with server.py implementing MCP protocol
- Added `mcp_servers.json` configuration file
- Updated `backend/main.py` with MCP initialization at startup, shutdown, and API endpoints
- Updated `backend/council.py` with tool detection and execution in stage1_collect_responses_streaming
- Updated `frontend/src/components/Stage1.jsx` to display tool results
- Updated `frontend/src/components/Stage1.css` with tool result card styling
- Updated `frontend/src/App.jsx` to handle tool_result events

---

### v0.5.2
**Branch:** `v0.5.2`  
**Completed:** 2025-11-27 09:57 UTC | 2025-11-27 01:57 PST

**Fixes:**
- **persist-timer-display**: Timer and tokens/s now persist after streaming completes
  - Previously, badges disappeared when `isStreaming` turned false
  - Frontend now shows badges whenever values exist, not just during streaming
  - Backend sends final timing info (thinking_seconds, elapsed_seconds) in model complete events
  - Added `get_final_timing()` method to TokenTracker class

**Changes:**
- `backend/council.py`: Added `get_final_timing()` method, included timing in all complete events
- `frontend/src/App.jsx`: Updated 6 model_complete handlers to capture final timing values
- `frontend/src/components/Stage1.jsx`: Show tps-badge and timing-badge without isStreaming check
- `frontend/src/components/Stage2.jsx`: Show tps-badge and timing-badge without isStreaming check
- `frontend/src/components/Stage3.jsx`: Show tps-badge and timing-badge without isStreaming check

---

### v0.5.1
**Branch:** `v0.5.1`  
**Completed:** 2025-11-27 09:51 UTC | 2025-11-27 01:51 PST

**Fixes:**
- **tokens-per-second-thinking**: Fixed tokens/s not displaying during thinking phase
  - Backend now sends `tokens_per_second` in all thinking events
  - Thinking tokens are counted toward overall TPS calculation
  - Frontend preserves TPS value when updating thinking state
- **console-spam-redux**: Additional cleanup of WebSocket console spam
  - Removed remaining print statements from WebSocket handler
  - Silenced client ID tracking for cleaner logs

**Changes:**
- `backend/council.py`: Extended `record_thinking()` to accept delta and return TPS
- `backend/council.py`: Added `tokens_per_second` to stage1/2/3 thinking events
- `frontend/src/App.jsx`: Added `tokensPerSecond` to all 6 thinking event handlers
- `backend/main.py`: Removed client_id prints from WebSocket handler
- `start.sh`: Already had `--log-level warning` from v0.4.1

---

### v0.5.0
**Branch:** `v0.5.0`  
**Completed:** 2025-11-27 09:44 UTC | 2025-11-27 01:44 PST

**Features:**
- **response-timing-display**: Real-time stopwatch showing thinking and total response time
  - Displays `<thinking_seconds>s/<total_seconds>s` format next to tokens/s
  - Shows timing in tab headers during streaming
  - Separate timing tracking for thinking vs response phases
  - Orange badge styling to differentiate from tok/s display

**Changes:**
- `backend/council.py`: Extended TokenTracker class with timing methods (record_thinking, mark_thinking_done, get_timing)
- `backend/council.py`: Added timing data to all stage token/thinking events
- `frontend/src/App.jsx`: Pass timing data (thinkingSeconds, elapsedSeconds) to streaming state
- `frontend/src/components/Stage1.jsx`: Display timing badge with formatTiming helper
- `frontend/src/components/Stage2.jsx`: Display timing badge with formatTiming helper
- `frontend/src/components/Stage3.jsx`: Display timing badge with formatTiming helper
- `frontend/src/components/Stage1.css`: Added timing-badge and timing-indicator styles
- `frontend/src/components/Stage2.css`: Added timing-badge and timing-indicator styles
- `frontend/src/components/Stage3.css`: Added timing-badge style

---

### v0.4.1
**Branch:** `v0.4.1`  
**Completed:** 2025-01-27 09:30 UTC | 2025-01-27 01:30 PST

**Fixes:**
- **console-spam**: Removed WebSocket connection/disconnection log messages
  - Silenced client connect/disconnect prints in backend
  - Set uvicorn log level to 'warning' in start.sh
- **tokens-display**: Fixed tokens/s not displaying during streaming
  - Removed `> 0` condition that hid initial values
  - Now shows tok/s only while actively streaming
  - Formatted to one decimal place for consistency

**Changes:**
- `backend/main.py`: Removed print statements from WebSocket handler
- `start.sh`: Added `--log-level warning` to uvicorn command
- `frontend/src/components/Stage1.jsx`: Fixed tps display conditions
- `frontend/src/components/Stage2.jsx`: Fixed tps display conditions
- `frontend/src/components/Stage3.jsx`: Fixed tps display conditions

---

### v0.4.0
**Branch:** `v0.4.0`  
**Completed:** 2025-01-27 08:52 UTC | 2025-01-27 00:52 PST

**Features:**
- **multi-round-deliberation**: Quality-based multi-round streaming deliberation
  - Stage 2 now runs multiple rounds if any response rated <30%
  - Each round: models rank AND rate (1-5) responses with feedback
  - Low-rated responses are refined based on peer feedback
  - Respects `max_rounds` config setting
- **tokens-per-second**: Real-time tokens/s display during streaming
  - Shows tok/s in tab headers and model labels
  - Updates in real-time as tokens stream
  - Final tok/s shown on completion
- **round-progress**: Round indicator in Stage 2 header
  - Shows "Round X / Y" during multi-round deliberation
  - Indicates "(Refinement)" for refinement rounds
  - Hidden for single-round deliberation

**Changes:**
- `backend/council.py`: Added TokenTracker class, quality rating extraction, multi-round streaming
- `backend/main.py`: Handle new stage2 return format with deliberation metadata
- `frontend/src/components/Stage1.jsx`: Display tokens/s
- `frontend/src/components/Stage2.jsx`: Display tokens/s and round indicator
- `frontend/src/components/Stage3.jsx`: Display tokens/s
- `frontend/src/App.jsx`: Handle round_start/round_complete events and tps data
- `frontend/src/components/*.css`: Styling for tps badges and round indicator

---

### v0.3.10
**Branch:** `v0.3.10`  
**Completed:** 2025-01-27 08:22 UTC | 2025-01-27 00:22 PST

**Fixes:**
- **remove-max-tokens**: Remove max_tokens limits causing truncation
  - Reasoning models use tokens for thinking AND response
  - 1024 max_tokens was cutting off responses mid-thought
  - Set all stages to `null` (unlimited, use model defaults)

**Changes:**
- `config.json`: `max_tokens` for stage1/2/3 set to `null`

---

### v0.3.9
**Branch:** `v0.3.9`  
**Completed:** 2025-01-27 08:15 UTC | 2025-01-27 00:15 PST

**Fixes:**
- **streaming-no-timeout**: Remove read timeout for streaming entirely
  - Reasoning models can pause for unlimited time between tokens
  - `read=None` allows stream to complete naturally
- **evaluation-timeout**: Increase evaluation timeout to 600s
  - Background evaluation uses council models (reasoning)
  - Was timing out at 120s
- **no-retries**: Set `max_retries: 0` to avoid wasted time
  - Long timeouts make retries unnecessary

**Changes:**
- `query_model_streaming()` now uses `read=None` (no timeout)
- All timeouts now 600s including evaluation
- `max_retries` set to 0

---

### v0.3.8
**Branch:** `v0.3.8`  
**Completed:** 2025-01-27 07:55 UTC | 2025-01-26 23:55 PST

**Fixes:**
- **timeout-increase-v2**: Increased all timeouts to 10 minutes (600s)
  - Reasoning models can think for 5+ minutes between chunks
  - `streaming_chunk_timeout`: 600s (new config)
  - `default_timeout`: 600s
  - `connection_timeout`: 30s (was 10s)
  - `evaluation_timeout`: 120s (was 60s)
  - `max_retries`: 1 (was 2, since timeout is longer)

**Changes:**
- `query_model()` now loads timeout from config instead of hardcoded 30s
- `query_model_streaming()` now loads timeout from config instead of hardcoded 300s
- All timeout functions use config values with sensible fallbacks

---

### v0.3.7
**Branch:** `v0.3.7`  
**Completed:** 2025-01-27 07:25 UTC | 2025-01-26 23:25 PST

**Fixes:**
- **empty-content-fallback**: Use reasoning_content when content is empty
  - Some models output everything in reasoning_content field
  - Stage1 and Stage3 now fallback to reasoning_content
- **streaming-timeout**: Fixed streaming timeout configuration
  - Read timeout now properly set for per-chunk waiting

**Changes:**
- Updated `council.py` stage1 and stage3 to use reasoning_content fallback
- Fixed httpx timeout config in `lmstudio.py` streaming

---

### v0.3.6
**Branch:** `v0.3.6`  
**Completed:** 2025-01-27 07:05 UTC | 2025-01-26 23:05 PST

**Fixes:**
- **timeout-increase**: Increased default timeout from 30s to 300s (5 minutes)
  - Reasoning models need more time for inference
  - Prevents repeated retries when model still thinking
  - Reduced max_retries from 3 to 2

**Changes:**
- Updated `config.json` timeout_config:
  - `default_timeout`: 30 → 300
  - `council_timeout`: 300 (new)
  - `chairman_timeout`: 300 (new)
  - `title_generation_timeout`: 60 → 300
  - `evaluation_timeout`: 60 (new, shorter for eval)
  - `max_retries`: 3 → 2
- Added `for_evaluation` parameter to `query_model_with_retry()`
- Updated all timeout references in council.py

---

### v0.3.5
**Branch:** `v0.3.5`  
**Completed:** 2025-01-27 06:48 UTC | 2025-01-26 22:48 PST

**Fixes:**
- **cleanup-invalid-models**: Removed test-model and test-model-2 from metrics
- **evaluator-selection**: Fixed evaluator to never be same as target model
  - Only uses valid council members or chairman
  - Uses second-best if target is highest-rated

**Changes:**
- Added `cleanup_invalid_models()` to `model_metrics.py`
- Added `get_valid_models()` and `get_evaluator_for_model()`
- Cleanup runs at server startup
- Each response evaluated by best available model (excluding itself)

---

### v0.3.4
**Branch:** `v0.3.4`  
**Completed:** 2025-01-27 06:07 UTC | 2025-01-26 22:07 PST

**Features:**
- **metrics-markdown**: Auto-generate `data/llm_metrics.md` alongside JSON
  - Rankings table with model, rating, success rate
  - Detailed scores for each model
  - Updates whenever metrics are recorded

**Changes:**
- Added `_save_metrics_markdown()` to `model_metrics.py`
- `save_metrics()` now generates both JSON and markdown

---

### v0.3.3
**Branch:** `v0.3.3`  
**Completed:** 2025-01-27 05:52 UTC | 2025-01-26 21:52 PST

**Fixes:**
- **metrics-logging**: Confirmed llm_metrics.json IS working (file in data/ folder)
- Added debug logging to metrics evaluation flow

**Features:**
- **markdown-export**: Final council answer saved as markdown file
  - Format: `<conversation_title>__utc_date_time.md`
  - Saved in project root (data/ parent folder)
  - Contains user query and final answer

**Changes:**
- Added `save_final_answer_markdown()` to `storage.py`
- Integrated markdown export into streaming endpoint
- Enhanced metrics evaluation logging for debugging

---

### v0.3.2
**Branch:** `v0.3.2`  
**Completed:** 2025-01-27 05:35 UTC | 2025-01-26 21:35 PST

**Fixes:**
- **metrics-file-path**: Fixed llm_metrics.json path to use data/ directory (was using cwd)
- **redo-duplicate-message**: Redo no longer creates duplicate user message

**Changes:**
- `model_metrics.py` now uses absolute path in `data/` directory
- Refactored `handleRedoMessage` and `handleEditMessage` to use `runCouncilForMessage()`
- New `runCouncilForMessage()` function runs council without adding user message

---

### v0.3.1
**Branch:** `v0.3.1`  
**Completed:** 2025-01-27 05:04 UTC | 2025-01-26 21:04 PST

**Fixes:**
- **retry-blank-responses**: Council members retry up to 2 times on blank/failed responses

**Features:**
- **model-quality-metrics**: Auto-evaluate responses to build quality metrics per model
  - Categories: verbosity, expertise, adherence, clarity, overall
  - Persistent storage in `llm_metrics.json`
  - Model ranking based on composite rating
  - API endpoints: `/api/metrics`, `/api/metrics/ranking`

**Changes:**
- Added `backend/model_metrics.py` for metrics tracking
- Retry logic in `stream_model()` with max 2 retries
- Background evaluation after Stage 1 responses
- New `stage1_model_retry` event for UI notification

---

### v0.3.0
**Branch:** `v0.3.0`  
**Completed:** 2025-01-27 04:17 UTC | 2025-01-26 20:17 PST

**Features:**
- **rich-formatting**: Enhanced Presenter prompt for tables, headers, code blocks, structured output
- **redo-message**: Redo icon (↻) to re-run council with same message
- **edit-message**: Edit icon (✎) to modify and resubmit message

**Changes:**
- Updated stage3 prompts to request rich markdown formatting
- Renamed "Chairman" to "Presenter" in UI for final answer stage
- Added message action buttons (redo/edit) on hover for user messages
- Added editing state with cancel option and visual indicator
- New handlers in App.jsx: `handleRedoMessage`, `handleEditMessage`

---

### v0.2.0
**Branch:** `v0.2.0`  
**Completed:** 2025-01-27 03:15 UTC | 2025-01-26 19:15 PST

**Fixes:**
- **app-title**: Changed web app title from "frontend" to "LLM Council (local)"

**Features:**
- **follow-up-input**: Input field now appears after Final Council Answer for follow-up questions
- **formatter-model**: Optional formatter LLM for Final Council Answer (falls back to chairman)

**Changes:**
- Updated `frontend/index.html` title
- Modified `ChatInterface.jsx` to show input form after stage3 completes
- Added `formatter` model config in `config.json` (empty = use chairman)
- Added `get_formatter_model()` in `config_loader.py`
- Updated `council.py` to use FORMATTER_MODEL for stage3 synthesis

---

### v0.1.0
**Branch:** `v0.1.0`  
**Completed:** 2025-01-27 01:25 UTC | 2025-01-26 17:25 PST

**Features:**
- **add-title-tooltip**: Conversation title tooltip on hover in sidebar
- **add-streaming-deliberation**: Real-time token streaming to UI for all deliberation stages
- **add-reactive-streaming**: Concise prompts and configurable max_tokens for faster responses

**Changes:**
- Added `query_model_streaming()` async generator for token-level streaming
- New `/api/conversations/{id}/message/stream-tokens` endpoint
- Frontend streaming state management with live content updates
- Thinking sections with collapsible display for reasoning models
- Visual streaming indicators (blinking cursor, progress badges)
- `response_config` in config.json for response style and token limits

---

## Format Reference

```markdown
### v<version>
**Branch:** `v<version>`  
**Completed:** YYYY-MM-DD HH:MM UTC | YYYY-MM-DD HH:MM <local-tz>

**Features:** (new capabilities)
- **feature-name**: Brief description

**Fixes:** (bug fixes)
- **fix-name**: Brief description

**Changes:** (implementation details)
- Technical detail 1
- Technical detail 2
```
