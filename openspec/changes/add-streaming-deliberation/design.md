## Context
This change transforms the batch-oriented deliberation display into a real-time streaming experience, requiring coordination between backend streaming APIs and frontend incremental rendering.

## Goals / Non-Goals
- Goals:
  - Real-time visibility into LLM processing as it happens
  - Progressive content display during all three stages
  - Support for reasoning model thinking tokens
- Non-Goals:
  - Changing the underlying deliberation logic
  - Adding new LLM capabilities
  - Modifying the council composition

## Decisions
- Decision: Use LM Studio's native streaming API (`stream: true`) to receive chunks
- Alternatives considered: 
  - Polling for partial results (rejected: inefficient, adds latency)
  - WebSocket for bidirectional (rejected: SSE sufficient for server-push)

- Decision: Stream tokens through existing SSE endpoint with new event types
- Alternatives considered:
  - Separate WebSocket connection (rejected: adds complexity, already have SSE)

- Decision: Accumulate tokens in frontend state, render progressively
- Alternatives considered:
  - DOM manipulation for each token (rejected: React anti-pattern)

## Risks / Trade-offs
- Risk: Increased frontend re-renders with high-frequency token updates → Mitigation: Batch token updates, debounce renders
- Risk: Network overhead from many small SSE events → Mitigation: Chunk tokens into reasonable batches (e.g., every 50ms)
- Risk: Partial content display during errors → Mitigation: Clear incomplete content on error, show fallback

## Open Questions
- Should thinking tokens be shown by default or collapsed?
- What batch interval provides best UX vs. performance trade-off?
