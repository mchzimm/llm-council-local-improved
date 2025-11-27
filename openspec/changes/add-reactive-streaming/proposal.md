# Change: Reactive Responses via Shorter LLM Output and Message Streaming

## Why
Current deliberation process waits for complete responses before displaying, creating long wait times. Shorter LLM responses combined with message streaming will make the UI feel more responsive and reduce perceived latency.

## What Changes
- Configure LLM prompts to encourage more concise, focused responses
- Implement token-by-token streaming to display responses as they generate
- Optimize prompt templates for brevity while maintaining quality
- Add configuration for response length limits

## Impact
- Affected specs: streaming-ui (extends add-streaming-deliberation)
- Affected code:
  - `backend/council.py`: Update stage prompts for conciseness
  - `backend/config.py`: Add response length configuration
  - `models.json`: Add max_tokens settings per model
  - Frontend components: Leverage streaming from add-streaming-deliberation
