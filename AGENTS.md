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

## Critical Rules

### Temporary Files - ALWAYS Use Project's tmp/ Folder
**⚠️ NEVER use system `/tmp/` directory. ALWAYS use the project's `tmp/` folder.**

- ✅ Correct: `tmp/test_results/`, `tmp/intake.md`, `./tmp/scratch.txt`
- ❌ Wrong: `/tmp/test.txt`, `/tmp/anything`

The project's `tmp/` folder is at `<project_root>/tmp/` and is used for:
- Test results (`tmp/test_results/`)
- Intake files (`tmp/intake.md`)
- Any temporary or scratch files needed during development

This ensures all temporary data stays within the project and is properly tracked/cleaned up.

### Intake File Management
When completing items from `tmp/intake.md`:
1. **Move completed items** to `tmp/intake-backup.md`
2. **Preserve instruction lines** - Do NOT move/change/remove lines starting with `**`
3. **Insert at top** - Place completed items underneath the first `**` line and above existing items
4. Format: Keep the original item text exactly as-is

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
4. **Run automated tests** after each change (see Testing Workflow below)

### Step 5: Update Tracking Files
After each completed change, use this checklist:

```
□ 1. CHANGELOG.md - Add entry with version, branch, timestamps (UTC + local)
□ 2. README.md - Update "Current Release" section (MANDATORY for features)
□ 3. FINDINGS.md - Document lessons learned and discoveries
□ 4. TODO.md - Remove completed item, move next item to Current
```

**⚠️ README.md Update is MANDATORY for all features:**
- For NEW features: Add entry under "Current Release" section (shift previous to "Previous Release")
- For FIX to existing feature: Update the relevant feature description if behavior changed
- Include: Feature name, bullet points describing capability, key technical details
- **Features without README updates are INCOMPLETE - do not commit without it**

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

### Git Hook Protection
A pre-commit hook prevents direct commits to master. If you see the error:
```
ERROR: Direct commits to 'master' are not allowed!
```
This means you forgot to create a version branch first. Follow the workflow below.

**Setup (after cloning):** Run `./setup-dev.sh` to install the git hooks.

The project follows semantic versioning with the format `<release>.<feature>.<fix>`:

### Version Number Rules

**Step 1: Classify the Change Type and Extent**

| Change Type | Description | Examples |
|-------------|-------------|----------|
| **Code Fix** | Bug fix in backend/logic | API error, calculation bug, null pointer |
| **Logic Fix** | Fix incorrect behavior | Wrong tool selection, bad routing |
| **UI Fix** | Visual bug fix | Broken layout, wrong colors, missing element |
| **UX Fix** | Interaction bug fix | Button not working, form not submitting |
| **UI Addition** | New visual element | New badge, icon, status indicator |
| **UX Addition** | New interaction/flow | New button action, keyboard shortcut |
| **Feature Addition** | New capability | New tool integration, new API endpoint |

| Extent | Description | Examples |
|--------|-------------|----------|
| **Minor** | Small, low-impact change | Tweak spacing, fix typo, add tooltip |
| **Major** | Significant, user-noticeable | New panel, new workflow, new integration |

**Step 2: Determine Version Increment**

```
FEATURE version (0.X.0) - increment middle number, reset fix to 0:
  ✓ Feature additions (any extent)
  ✓ Major UI additions (new panels, significant visual changes)
  ✓ Major UX additions (new workflows, significant interaction changes)

FIX version (0.x.Y) - increment last number only:
  ✓ All bug fixes (code, logic, UI, UX)
  ✓ Minor UI additions (small visual tweaks)
  ✓ Minor UX additions (small interaction improvements)
```

**Examples:**
- `v0.30.3 → v0.31.0`: Adding new MCP tool integration (feature)
- `v0.30.3 → v0.31.0`: Adding collapsible side panel (major UI addition)
- `v0.30.3 → v0.30.4`: Fixing null pointer error (code fix)
- `v0.30.3 → v0.30.4`: Adding loading spinner to button (minor UI addition)
- `v0.30.3 → v0.30.4`: Fixing wrong tool being selected (logic fix)

**Release** (x.0.0): Increment when all major features are implemented to completion (confirmed by user)

**⚠️ CRITICAL: Version numbers must be sequential and monotonically increasing!**
- Always base the next version on the HIGHEST existing version number
- Never create a fix version (0.x.y) that is lower than an existing feature version
- Example: If v0.14.0 exists, next fix must be v0.14.1, NOT v0.8.x

### ⚠️ MANDATORY COMPLETION CHECKLIST

**Before marking ANY task complete, verify ALL items:**

```
□ 1. VERSION BRANCH created (git checkout -b v<x.y.z>)
□ 2. CODE CHANGES implemented and working
□ 3. TESTS PASS (uv run -m tests.test_runner)
□ 4. README.md UPDATED (Current Release section)
□ 5. CHANGELOG.md UPDATED (version entry with timestamps)
□ 6. TODO.md UPDATED (remove completed, move next to Current)
□ 7. COMMITTED (git add -A && git commit -m "v<x.y.z>: description")
□ 8. PUSHED to feature branch (git push -u origin v<x.y.z>)
□ 9. MERGED to master (git checkout master && git merge v<x.y.z>)
□ 10. PUSHED master (git push origin master)
```

**README.md Update Requirements:**
- Add entry under "Current Release (v<x.y.z>)" section
- Shift previous "Current Release" to "Previous Release"
- Include: Feature name, bullet points, technical details
- **Features without README updates are INCOMPLETE**

### Mandatory Workflow (Follow These Steps In Order)

**Step 1: Classify Change & Determine Next Version**
```bash
# CRITICAL: Find the highest version number first
git branch -a | grep -oE "v[0-9]+\.[0-9]+\.[0-9]+" | sort -V | tail -1
```

1. **Classify your change** using the table above (type + extent)
2. **Determine version increment**:
   - Feature additions OR major UI/UX additions → increment FEATURE (middle): `v0.30.3 → v0.31.0`
   - Bug fixes OR minor additions → increment FIX (last): `v0.30.3 → v0.30.4`
3. **NEVER go backwards** - if v0.14.0 exists, next version must be v0.14.x or v0.15.0+

**Step 2: Create Version Branch BEFORE Coding**
```bash
git checkout -b v<new-version>  # e.g., git checkout -b v0.4.0
```

**Step 3: Implement Changes**
- Make all code changes on the version branch
- Keep changes focused on the proposal scope
- **Run tests after each significant change**: `uv run -m tests.test_runner`
- Fix any test failures before proceeding

**Step 4: Run Final Test Suite**
```bash
uv run -m tests.test_runner  # All tests MUST pass before committing
```

**Step 5: Update Documentation (BEFORE committing)**
⚠️ **MANDATORY - do NOT skip any item:**

```
□ README.md - Update "Current Release" section with new feature/fix
□ CHANGELOG.md - Add version entry with timestamps (UTC + local)
□ FINDINGS.md - Document any discoveries or lessons learned (if applicable)
```

**Step 6: Commit Changes**
```bash
git add -A
git commit -m "v<version>: <brief description of changes>"
```

**Step 6: Commit and Push to Feature Branch**
```bash
git add -A
git commit -m "v<version>: <brief description>"
git push -u origin v<new-version>
```

**Step 7: Merge to Master and Sync (IMMEDIATELY after tests pass)**
```bash
git checkout master
git merge v<new-version>
git push origin master
```

**⚠️ CRITICAL: Steps 6-7 must be completed in the SAME session once all tests pass!**
- Do NOT wait for separate approval - merge immediately after successful tests
- This ensures GitHub repo stays in sync with local changes
- Failing to complete Step 7 leaves changes orphaned on feature branch only

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

### Automated Testing Framework

The project includes automated tests in `tests/`. Run tests to validate changes:

```bash
# Run all tests (auto-starts/stops server)
uv run -m tests.test_runner

# Run specific scenario
uv run -m tests.test_runner --scenario current_news_websearch

# Filter by tags (mcp, websearch, factual, deliberation, etc.)
uv run -m tests.test_runner --tags mcp

# Use existing running server (disable auto-management)
uv run -m tests.test_runner --no-auto-server

# Run with multiple iterations (auto-retry on failures)
uv run -m tests.test_runner --max-iterations 3
```

**Test Scenarios** are defined in `tests/scenarios.json`. Each scenario specifies:
- `query`: The test input
- `expected_behavior`: Checks to validate (tool_used, contains, no_refusal, etc.)
- `tags`: Categories for filtering

### Testing Workflow (MANDATORY)

**CRITICAL: Run tests during every implementation cycle.**

#### During Implementation
1. **Before coding**: Run relevant tests to establish baseline
   ```bash
   uv run -m tests.test_runner --tags <relevant-tags>
   ```

2. **After each significant change**: Re-run tests
   ```bash
   uv run -m tests.test_runner
   ```

3. **CRITICAL: After EVERY test run, verify test results were generated:**
   ```bash
   # Check that a new result file was created in tmp/test_results/
   ls -la tmp/test_results/ | tail -5
   ```
   - **If no new file**: The test did not complete - investigate why
   - **If file exists**: Open and evaluate the result JSON

4. **Evaluate test results** (check the JSON file):
   - Look at `"passed"` and `"failed"` counts at the top level
   - If `"failed" > 0`: Test was UNSUCCESSFUL
   - For each failed test, check:
     - `"name"`: Which scenario failed
     - `"actual"`: What the system returned
     - `"expected"`: What was expected
     - `"details.checks"`: Which specific checks failed (second element is `false`)
   - Example of failed check: `["contains", false, ["expected_term"]]`

5. **On test failure**: 
   - Analyze the failure report in `tmp/test_results/`
   - Identify the root cause from the `"actual"` response
   - Fix the issue in the code
   - Re-run tests
   - Verify new test result file was generated
   - Iterate until `"failed": 0` in test results

6. **Before committing**: All relevant tests MUST pass
   ```bash
   uv run -m tests.test_runner  # Full test suite
   # Then verify: tmp/test_results/ has new file with "failed": 0
   ```

7. **After ALL tests pass**: Commit, merge to master, and push IMMEDIATELY
   ```bash
   git add -A
   git commit -m "v<version>: <description>"
   git push -u origin v<version>
   git checkout master
   git merge v<version>
   git push origin master
   ```
   **⚠️ Do NOT skip the merge step - changes must sync to GitHub in the same session!**

#### Adding Tests for New Features
When implementing a new feature:
1. Add a test scenario to `tests/scenarios.json`
2. Include appropriate tags (mcp, deliberation, ui, etc.)
3. Define expected_behavior with relevant checks
4. Run the new test to verify the feature works

#### Test Result JSON Structure Quick Reference
```json
{
  "timestamp": "YYYYMMDD_HHMMSS",
  "passed": 7,           // ← Must equal "total" for success
  "failed": 0,           // ← Must be 0 for success
  "total": 7,
  "results": [
    {
      "name": "test_name",
      "passed": true,    // ← Individual test status
      "expected": {...}, // ← What we checked for
      "actual": "...",   // ← What the system returned
      "details": {
        "checks": [
          ["check_type", true, "context"],  // ← true = passed
          ["check_type", false, "context"]  // ← false = FAILED
        ]
      }
    }
  ]
}
```

#### Test Tags Reference
- `mcp` - MCP tool integration tests
- `websearch` - Web search functionality
- `calculator` - Calculator tool tests
- `datetime` - Date/time tool tests
- `geolocation` - Geolocation tool tests
- `factual` - Simple factual queries (no deliberation)
- `deliberation` - Full council deliberation tests
- `chat` - Basic chat/greeting tests
- `current-events` - Real-time data awareness tests
- `regression` - Regression tests for known issues

### Manual Testing

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

## Memory Integration (Graphiti)

### Overview
The memory service integrates with the Graphiti MCP server to provide persistent memory across conversations. It records all messages and can provide fast-path responses when confidence is high enough.

### Memory Flow
```
User Query
    ↓
Memory Check (if Graphiti available)
    ↓
If confidence >= threshold → Memory-based response (skip LLM)
    ↓ else
Standard workflow (classification → tools → routing)
    ↓
Async: Record query & response to Graphiti
```

### Configuration (`config.json`)
```json
{
  "models": {
    "confidence": {
      "id": "",
      "name": "Memory Confidence Scorer",
      "description": "Model for scoring memory relevance (empty = use chairman)"
    }
  },
  "memory": {
    "enabled": true,
    "confidence_threshold": 0.8,
    "max_memory_age_days": 30,
    "group_id": "llm_council",
    "record_user_messages": true,
    "record_council_responses": true,
    "record_chairman_synthesis": true
  }
}
```

### Key Components
- **`backend/memory_service.py`**: MemoryService class for Graphiti interaction
- **Recording**: Async, non-blocking recording of all messages
- **Retrieval**: Searches facts and nodes, calculates confidence score
- **Fallback**: Gracefully continues standard workflow if Graphiti unavailable

### API Endpoint
- `GET /api/memory/status` - Returns memory service status and configuration
