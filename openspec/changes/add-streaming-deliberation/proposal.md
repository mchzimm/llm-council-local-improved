# Change: Stream LLM Thinking and Responses to Web UI

## Why
Users currently wait for each stage to complete before seeing any output. Real-time streaming of LLM thinking and responses provides immediate feedback and visibility into the deliberation process.

## What Changes
- Stream LLM token output in real-time to the web UI during all three deliberation stages
- Display thinking/reasoning tokens from reasoning models as they are generated
- Show partial response content progressively during generation
- **BREAKING**: Frontend must handle incremental updates instead of complete stage responses

## Impact
- Affected specs: streaming-ui (new)
- Affected code: 
  - `backend/lmstudio.py`: Add streaming support to model queries
  - `backend/council.py`: Integrate streaming into stage processing
  - `backend/main.py`: Stream events through SSE endpoint
  - `frontend/src/api.js`: Handle streaming token events
  - `frontend/src/App.jsx`: Update state incrementally with tokens
  - `frontend/src/components/Stage1.jsx`, `Stage2.jsx`, `Stage3.jsx`: Render streaming content
