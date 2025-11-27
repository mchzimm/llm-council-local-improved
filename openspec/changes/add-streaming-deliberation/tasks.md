## 1. Backend Streaming Infrastructure
- [x] 1.1 Add `stream=True` parameter support to `query_model()` in `lmstudio.py`
- [x] 1.2 Implement async generator for streaming tokens from LM Studio API
- [x] 1.3 Handle `reasoning_details` streaming for thinking models
- [x] 1.4 Create token streaming wrapper that yields chunks

## 2. Council Stage Streaming
- [x] 2.1 Modify `stage1_collect_responses()` to stream individual model responses
- [x] 2.2 Add streaming events: `model_token`, `model_thinking`, `model_complete`
- [x] 2.3 Modify `stage2_collect_rankings()` to stream evaluation text
- [x] 2.4 Modify `stage3_synthesize_final()` to stream chairman response

## 3. SSE Event Enhancement
- [x] 3.1 Add token-level SSE events to streaming endpoint
- [x] 3.2 Define event types: `stage1_token`, `stage1_thinking`, `stage2_token`, `stage3_token`
- [x] 3.3 Include model identifier and stage context in each event

## 4. Frontend Token Handling
- [x] 4.1 Update `api.js` to handle granular token events
- [x] 4.2 Modify `App.jsx` to update message content incrementally
- [x] 4.3 Add streaming content state management

## 5. UI Streaming Display
- [x] 5.1 Update `Stage1.jsx` to render content as it streams
- [x] 5.2 Add thinking display with collapsible reasoning tokens
- [x] 5.3 Update `Stage2.jsx` to show streaming evaluations
- [x] 5.4 Update `Stage3.jsx` to display streaming synthesis
- [x] 5.5 Add visual indicator for active streaming (blinking cursor, etc.)
