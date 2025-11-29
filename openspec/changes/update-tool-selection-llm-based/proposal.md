# Proposal: LLM-Based Tool Selection and Iterative Assessment

## Summary
Replace regex-based math detection with LLM-based tool selection, and add iterative tool assessment after each deliberation step to determine if additional tool calls would be helpful.

## Motivation
- Current regex-based math detection causes false positives (e.g., "and/or" triggering calculator)
- Tool selection happens only once at the start; subsequent steps cannot request additional data
- LLM-based selection is more flexible and context-aware than pattern matching

## Scope

### Change 1: LLM-Based Initial Tool Selection
- Remove regex-based math detection override in `_analyze_user_expectations()`
- Trust the LLM's initial analysis for tool selection
- Keep the two-step process (expectations → tool mapping) but remove pattern-matching overrides

### Change 2: Iterative Tool Assessment After Deliberation Steps
- After Stage 1 (individual responses), assess if additional tools would help
- After Stage 2 (rankings), assess if additional tools would help before synthesis
- Use `tool_calling` model to evaluate need for additional data
- Execute tool calls if recommended, then continue to next step

## Design Considerations
- Use existing `tool_calling` model configuration
- Assessment prompt should include current context (stage output) and available tools
- Limit iterations to prevent infinite loops (max 2 additional tool calls per stage)
- Tool results should be injected into the next stage's context

## Affected Components
- `backend/council.py`: `_analyze_user_expectations()`, deliberation flow
- Tool assessment prompts and logic

## Risk Assessment
- **Medium Risk**: Changes core deliberation flow
- **Mitigation**: Add configuration flag to enable/disable iterative assessment
- **Mitigation**: Comprehensive testing with existing scenarios

## Success Criteria
- Queries like "20 types of fruits and/or vegetables" should NOT trigger calculator
- Deliberation can request websearch mid-flow if initial responses lack data
- No regression in existing test scenarios
