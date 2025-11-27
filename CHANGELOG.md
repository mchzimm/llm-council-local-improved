# Changelog

Completed changes with version, branch, and timestamp information.

## Completed Changes

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
