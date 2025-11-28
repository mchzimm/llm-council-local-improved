# Change: Add MCP Status Indicator to Header

## Why
Users need visibility into MCP server status and tool availability directly from the UI. Currently, MCP status is only accessible via API calls, making it difficult to know if tools are available, busy, or offline.

## What Changes
- Add "MCP" badge next to "LLM Council" title in sidebar header
- Blue bold text with light grey edge styling, same size as title
- Hover overlay showing MCP servers with status indicators (red/yellow/green for offline/busy/available)
- Secondary hover overlay on servers showing their tools with real-time status
- Metrics display at bottom of each overlay

## Impact
- Affected specs: None (new capability)
- Affected code: `frontend/src/components/Sidebar.jsx`, `frontend/src/components/Sidebar.css`, `frontend/src/api.js`
- Backend already has `/api/mcp/status` endpoint providing server/tool info
