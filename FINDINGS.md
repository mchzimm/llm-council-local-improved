# Findings & Lessons Learned

Documentation of discoveries, insights, and lessons learned during implementation.

---

## v0.1.0 - Streaming Implementation

### Finding: SSE Event Buffering Requires Careful Handling
**Summary:** Server-Sent Events may arrive in partial chunks, requiring buffer management on the frontend.

**Details:**
When implementing token streaming via SSE, the frontend initially missed some events because:
1. Multiple `data:` lines can arrive in a single chunk
2. Lines can be split across chunks
3. The decoder needs `{ stream: true }` option

**Solution:**
```javascript
let buffer = '';
buffer += decoder.decode(value, { stream: true });
const lines = buffer.split('\n');
buffer = lines.pop() || ''; // Keep incomplete line in buffer
```

**Lesson:** Always implement buffering for SSE clients, don't assume one chunk = one event.

---

### Finding: Async Generator Pattern for Streaming
**Summary:** Python async generators provide clean abstraction for streaming LLM responses.

**Details:**
The `query_model_streaming()` function uses `async for` with `yield` to provide tokens as they arrive:
```python
async def query_model_streaming(...) -> AsyncGenerator[Dict, None]:
    async for line in response.aiter_lines():
        yield {"type": "token", "delta": content_delta}
```

This pattern allows:
- Clean separation of streaming logic from business logic
- Easy composition with `async for chunk in query_model_streaming(...)`
- Natural backpressure handling

**Lesson:** Async generators are the idiomatic Python pattern for streaming data.

---

### Finding: Versioning Process Must Be Front-and-Center
**Summary:** Burying versioning instructions deep in documentation leads to them being skipped.

**Details:**
The versioning process was documented but not followed because:
1. Instructions were at line 160+ in AGENTS.md
2. No prominent warning at document start
3. OpenSpec workflow didn't explicitly require it

**Solution:**
- Added warning banner at top of AGENTS.md
- Made versioning Step 1 in OpenSpec implementation workflow
- Added explicit bash commands for each step

**Lesson:** Critical processes need prominent placement and explicit triggers in workflow documentation.

---

## Format Reference

```markdown
## v<version> - <Brief Context>

### Finding: <Title>
**Summary:** One-line description of the finding.

**Details:**
Detailed explanation of what was discovered, including:
- Context and background
- Technical details
- Code examples if relevant

**Solution:** (if applicable)
How the issue was resolved or the insight was applied.

**Lesson:** Key takeaway for future reference.
```
