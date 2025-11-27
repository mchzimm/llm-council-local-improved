<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# CLAUDE.md - Technical Notes for LLM Council

**⚠️ BEFORE IMPLEMENTING ANY CHANGES:**
1. **Read "Change Request Handling" section** - Analyze and prioritize requests
2. **Update TODO.md** - Add items in correct priority order
3. **Follow "Versioning Process"** - Create version branch FIRST
4. **After completion** - Update CHANGELOG.md, FINDINGS.md, and README.md

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Change Request Handling

**CRITICAL: Follow this process when receiving ANY change request from user.**

### Step 1: Analyze the Request
1. **Identify all changes requested** - List each distinct change
2. **Classify each change**:
   - `[FIX]` - Bug fix or correction to existing feature
   - `[FEATURE]` - New capability or enhancement
   - `[REFACTOR]` - Code improvement without behavior change
   - `[DOCS]` - Documentation update

### Step 2: Prioritize Changes
**Priority Order (implement in this sequence):**
1. **Fixes** - Always implement bug fixes before new features
2. **Features** - New capabilities after fixes are complete
3. **Refactors** - Code improvements after features
4. **Docs** - Documentation updates last (unless blocking)

### Step 3: Update TODO.md
Add items to appropriate section:
- **Current** (max 3): Items being worked on now
- **Next** (max 5): Queued for after Current
- **Future**: Ideas for later

Format:
```markdown
- [ ] **[TYPE]** Brief description
  - Acceptance criteria
  - Related files
```

### Step 4: Implement in Order
1. Work through TODO.md: Current → Next → Future
2. Complete each item fully before starting next
3. Follow versioning process for each implementation session

### Step 5: Update Tracking Files
After each completed change:
1. **CHANGELOG.md** - Add entry with version, branch, timestamps (UTC + local)
2. **FINDINGS.md** - Document lessons learned and discoveries
3. **README.md** - Update feature list (features only, not fixes)
4. **TODO.md** - Remove completed item, move next item to Current

## Project Overview

LLM Council is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2, preventing models from playing favorites.

## Architecture

### Backend Structure (`backend/`)

**`config.py`**
- Contains `COUNCIL_MODELS` (list of LM Studio model identifiers)
- Contains `CHAIRMAN_MODEL` (model that synthesizes final answer)
- Uses optional environment variable `LM_STUDIO_BASE_URL` from `.env` (defaults to `http://192.168.1.111:11434`)
- Backend runs on **port 8001** (NOT 8000 - user had another app on 8000)

**`lmstudio.py`** (formerly `openrouter.py`)
- `query_model()`: Single async model query to LM Studio
- `query_models_parallel()`: Parallel queries using `asyncio.gather()`
- Returns dict with 'content' and optional 'reasoning_details'
- Graceful degradation: returns None on failure, continues with successful responses
- No authentication required (local network API)

**`council.py`** - The Core Logic
- `stage1_collect_responses()`: Parallel queries to all council models
- `stage2_collect_rankings()`:
  - Anonymizes responses as "Response A, B, C, etc."
  - Creates `label_to_model` mapping for de-anonymization
  - Prompts models to evaluate and rank (with strict format requirements)
  - Returns tuple: (rankings_list, label_to_model_dict)
  - Each ranking includes both raw text and `parsed_ranking` list
- `stage3_synthesize_final()`: Chairman synthesizes from all responses + rankings
- `parse_ranking_from_text()`: Extracts "FINAL RANKING:" section, handles both numbered lists and plain format
- `calculate_aggregate_rankings()`: Computes average rank position across all peer evaluations

**`storage.py`**
- JSON-based conversation storage in `data/conversations/`
- Each conversation: `{id, created_at, messages[]}`
- Assistant messages contain: `{role, stage1, stage2, stage3}`
- Note: metadata (label_to_model, aggregate_rankings) is NOT persisted to storage, only returned via API

**`main.py`**
- FastAPI app with CORS enabled for localhost:5173 and localhost:3000
- POST `/api/conversations/{id}/message` returns metadata in addition to stages
- Metadata includes: label_to_model mapping and aggregate_rankings

### Frontend Structure (`frontend/src/`)

**`App.jsx`**
- Main orchestration: manages conversations list and current conversation
- Handles message sending and metadata storage
- Important: metadata is stored in the UI state for display but not persisted to backend JSON

**`components/ChatInterface.jsx`**
- Multiline textarea (3 rows, resizable)
- Enter to send, Shift+Enter for new line
- User messages wrapped in markdown-content class for padding

**`components/Stage1.jsx`**
- Tab view of individual model responses
- ReactMarkdown rendering with markdown-content wrapper

**`components/Stage2.jsx`**
- **Critical Feature**: Tab view showing RAW evaluation text from each model
- De-anonymization happens CLIENT-SIDE for display (models receive anonymous labels)
- Shows "Extracted Ranking" below each evaluation so users can validate parsing
- Aggregate rankings shown with average position and vote count
- Explanatory text clarifies that boldface model names are for readability only

**`components/Stage3.jsx`**
- Final synthesized answer from chairman
- Green-tinted background (#f0fff0) to highlight conclusion

**Styling (`*.css`)**
- Light mode theme (not dark mode)
- Primary color: #4a90e2 (blue)
- Global markdown styling in `index.css` with `.markdown-content` class
- 12px padding on all markdown content to prevent cluttered appearance

## Key Design Decisions

### Stage 2 Prompt Format
The Stage 2 prompt is very specific to ensure parseable output:
```
1. Evaluate each response individually first
2. Provide "FINAL RANKING:" header
3. Numbered list format: "1. Response C", "2. Response A", etc.
4. No additional text after ranking section
```

This strict format allows reliable parsing while still getting thoughtful evaluations.

### De-anonymization Strategy
- Models receive: "Response A", "Response B", etc.
- Backend creates mapping: `{"Response A": "openai/gpt-5.1", ...}`
- Frontend displays model names in **bold** for readability
- Users see explanation that original evaluation used anonymous labels
- This prevents bias while maintaining transparency

### Error Handling Philosophy
- Continue with successful responses if some models fail (graceful degradation)
- Never fail the entire request due to single model failure
- Log errors but don't expose to user unless all models fail

### UI/UX Transparency
- All raw outputs are inspectable via tabs
- Parsed rankings shown below raw text for validation
- Users can verify system's interpretation of model outputs
- This builds trust and allows debugging of edge cases

## Important Implementation Details

### Relative Imports
All backend modules use relative imports (e.g., `from .config import ...`) not absolute imports. This is critical for Python's module system to work correctly when running as `python -m backend.main`.

### Port Configuration
- Backend: 8001 (changed from 8000 to avoid conflict)
- Frontend: 5173 (Vite default)
- Update both `backend/main.py` and `frontend/src/api.js` if changing

### Markdown Rendering
All ReactMarkdown components must be wrapped in `<div className="markdown-content">` for proper spacing. This class is defined globally in `index.css`.

### Model Configuration
Models are now configured via `models.json` file instead of hardcoded values in `backend/config.py`. Current models are local via LM Studio:
- Council: Phi-4 Mini Reasoning, Apollo 4B Thinking, AI21 Jamba Reasoning
- Chairman: Qwen3-4B Thinking
- Configuration supports runtime changes without code modifications

## Common Gotchas

1. **Module Import Errors**: Always run backend as `python -m backend.main` from project root, not from backend directory
2. **CORS Issues**: Frontend must match allowed origins in `main.py` CORS middleware
3. **LM Studio Connection**: Ensure LM Studio server is running and all models are loaded before starting
4. **Local Network**: Backend requires network access to LM Studio server at configured IP
5. **Ranking Parse Failures**: If models don't follow format, fallback regex extracts any "Response X" patterns in order
6. **Missing Metadata**: Metadata is ephemeral (not persisted), only available in API responses

## Versioning Process

**CRITICAL: Follow this process BEFORE implementing any OpenSpec proposal or code change.**

The project follows semantic versioning with the format `<release>.<feature>.<fix>`:

### Version Number Rules
- **Release** (x.0.0): Increment when all major features are implemented to completion (confirmed by user)
- **Feature** (0.x.0): Increment whenever a new feature is implemented
- **Fix** (0.0.x): Increment with every bug fix being implemented

### Mandatory Workflow (Follow These Steps In Order)

**Step 1: Determine Next Version**
```bash
git branch -a | grep "v[0-9]"  # List version branches
```
- If implementing features: increment middle number (e.g., v0.3.0 → v0.4.0)
- If fixing bugs: increment last number (e.g., v0.3.0 → v0.3.1)
- Multiple features in one session: use single feature increment

**Step 2: Create Version Branch BEFORE Coding**
```bash
git checkout -b v<new-version>  # e.g., git checkout -b v0.4.0
```

**Step 3: Implement Changes**
- Make all code changes on the version branch
- Keep changes focused on the proposal scope

**Step 4: Commit Changes**
```bash
git add -A
git commit -m "v<version>: <brief description of changes>"
```

**Step 5: Push Branch to Remote**
```bash
git push -u origin v<new-version>
```

**Step 6: Merge to Master (when approved)**
```bash
git checkout master
git merge v<new-version>
git push origin master
```

### Branch Naming Convention
Version branches: `v<release>.<feature>.<fix>` (e.g., `v0.1.0`, `v1.2.3`)

## Future Enhancement Ideas

- Configurable council/chairman via UI instead of config file
- Streaming responses instead of batch loading
- Export conversations to markdown/PDF
- Model performance analytics over time
- Custom ranking criteria (not just accuracy/insight)
- Support for reasoning models (o1, etc.) with special handling

## Testing Notes

Test LM Studio connectivity with a simple Python script:
```python
import asyncio
from backend.lmstudio import query_model
response = await query_model('microsoft/phi-4-mini-reasoning', [{'role': 'user', 'content': 'test'}])
```

Ensure all models are loaded in LM Studio before testing council functionality.

## Data Flow Summary

```
User Query
    ↓
Stage 1: Parallel queries to LM Studio models → [individual responses]
    ↓
Stage 2: Anonymize → Parallel ranking queries → [evaluations + parsed rankings]
    ↓
Aggregate Rankings Calculation → [sorted by avg position]
    ↓
Stage 3: Chairman synthesis via LM Studio with full context
    ↓
Return: {stage1, stage2, stage3, metadata}
    ↓
Frontend: Display with tabs + validation UI
```

All API calls go to local LM Studio server. The entire flow is async/parallel where possible to minimize latency.
