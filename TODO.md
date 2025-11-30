# TODO Tracker

This file tracks pending changes organized by priority. AI agents should process items from **Current** first, then **Next**, then **Future**.

## Current
<!-- Items actively being worked on. Maximum 3 items. -->

(No current items)

## Next
<!-- Items queued for implementation after Current is complete. Maximum 5 items. -->

## Future
<!-- Ideas and enhancements for later consideration. No limit. -->

- [ ] **[FEATURE]** Multi-round quality assessment loop
  - Chairman evaluates final answer against original question
  - Compiles list of shortcomings (unanswered aspects, missing details)
  - If shortcomings found, triggers another deliberation round with feedback
  - Council receives: original question, previous answer, shortcomings list
  - Loop continues until chairman satisfied or max rounds reached
  - Config: max_quality_rounds setting
  - Related: backend/council.py, backend/config.py
  - Reference: conversation 54708a99 (apocalyptic scenarios - answer was comparison table not actual list)

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
