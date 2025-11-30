# TODO Tracker

This file tracks pending changes organized by priority. AI agents should process items from **Current** first, then **Next**, then **Future**.

## Current
<!-- Items actively being worked on. Maximum 3 items. -->

- [ ] **[FIX]** Thinking mode auto-scroll within text area
  - Auto-scroll to bottom while thoughts streaming
  - Disable if user scrolls up within that element
  - Related: frontend/src/components/Stage*.jsx

## Next
<!-- Items queued for implementation after Current is complete. Maximum 5 items. -->

- [ ] **[FEATURE]** Graphiti brain emoji indicator
  - Show 🧠 message with details when Graphiti MCP is used
  - Needs backend event emission for memory operations
  - Related: backend/memory_service.py, frontend/src/App.jsx

## Future
<!-- Ideas and enhancements for later consideration. No limit. -->

- [ ] **[REFACTOR]** Config restructure - providers, individuals, teams, support
  - New structure with inference providers, model definitions, personalities
  - Teams with member_count, shared personality traits
  - Support roles (formatter, tool_calling, prompt_engineer)
  - Breaking change - requires migration script
  - See intake request from 2025-11-29 for full spec

---

## Guidelines for AI Agents

### Processing Order
1. **Fixes before Features**: Bug fixes take priority over new features
2. **Current → Next → Future**: Work through sections in order
3. **One at a time**: Complete current item before starting next

### Adding Items
- **Fixes**: Add to Current (if < 3 items) or top of Next
- **Features**: Add to Next (if < 5 items) or Future
- **Ideas**: Add to Future

### Item Format
```markdown
- [ ] **[TYPE]** Brief description
  - Details or acceptance criteria
  - Related files or components
```

Types: `[FIX]`, `[FEATURE]`, `[REFACTOR]`, `[DOCS]`

### Moving Items
- When starting work: Move from Next → Current
- When blocked: Move back to Next with note
- When complete: Remove from TODO, add to CHANGELOG.md
