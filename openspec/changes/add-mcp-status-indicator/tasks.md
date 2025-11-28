# Tasks: Add MCP Status Indicator

## 1. Backend Enhancements
- [x] 1.1 Add server status tracking (available/busy/offline) to MCP registry
- [x] 1.2 Add tool in-use tracking to MCP registry
- [ ] 1.3 Create WebSocket endpoint for real-time MCP status updates (deferred - using polling)

## 2. Frontend - MCP Badge
- [x] 2.1 Add "MCP" badge next to title in Sidebar header
- [x] 2.2 Style badge: blue bold text, light grey edge/border, same size as title

## 3. Frontend - Server Status Overlay
- [x] 3.1 Create hover trigger for title area (including "LLM Council" and "MCP")
- [x] 3.2 Create semi-transparent dark overlay (20% transparency) with server list
- [x] 3.3 Add status indicators: red (offline), yellow (busy), green (available)
- [x] 3.4 Add metrics section showing server count, tools available

## 4. Frontend - Tool Status Overlay  
- [x] 4.1 Create secondary hover overlay when hovering individual servers
- [x] 4.2 List all tools for hovered server
- [x] 4.3 Highlight tools in yellow when in-use (real-time updates)
- [x] 4.4 Add metrics section showing tool count, active tools

## 5. API Integration
- [x] 5.1 Add API function to fetch MCP status
- [ ] 5.2 Connect WebSocket for real-time status updates (deferred - using polling)
- [x] 5.3 Implement periodic polling fallback if WebSocket unavailable

## 6. Testing
- [ ] 6.1 Test overlay positioning and visibility
- [ ] 6.2 Test status indicator colors
- [ ] 6.3 Test real-time tool in-use highlighting
- [ ] 6.4 Test with MCP servers in various states
