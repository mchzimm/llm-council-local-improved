# Tasks: LLM-Based Tool Selection and Iterative Assessment

## Phase 1: Remove Regex Overrides
- [x] Remove regex-based math detection override in `_analyze_user_expectations()`
- [x] Keep word-based indicators but remove operator regex check
- [x] Trust LLM for tool selection decisions
- [ ] Test: "20 types of fruits and/or vegetables" should NOT trigger calculator
- [ ] Test: "what is 5 plus 3" should still trigger calculator (via LLM)

## Phase 2: Add Iterative Tool Assessment
- [x] Create `assess_tool_needs_mid_deliberation()` function for mid-deliberation assessment
- [x] Add assessment after Stage 1 completion
- [x] Add assessment after Stage 2 completion (before Stage 3)
- [x] Implement tool execution for mid-flow requests (websearch only)
- [x] Add max iteration limit (1 per stage, websearch only)

## Phase 3: Configuration and Testing
- [ ] Run full test suite
- [ ] Test with nutrition query that needs websearch
- [ ] Test with calculation query to ensure math still works
- [ ] Update CHANGELOG.md

## Acceptance Criteria
- [x] No regex overrides for tool selection
- [x] Iterative tool assessment functional
- [ ] All existing tests pass
- [ ] New test scenarios pass
