# Change: Add Delayed Close for MCP Overlay Groups

## Why
Currently, the MCP server overlay and tools overlay close immediately when the cursor leaves their area. This makes it difficult to navigate from the server list to a specific server's tools overlay, as any slight cursor movement outside the overlays causes them to close instantly.

## What Changes
- Add a 2-second delay before closing overlays when cursor leaves
- Group the MCP server overlay and tools overlay as a single "overlay group"
- Only start the close timer if cursor is outside ALL overlays in the group
- Cancel the timer if cursor re-enters any overlay in the group

## Impact
- Affected specs: ui (new)
- Affected code: `frontend/src/components/Sidebar.jsx`, `frontend/src/components/Sidebar.css`
