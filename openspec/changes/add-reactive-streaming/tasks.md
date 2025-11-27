## 1. Prompt Optimization for Brevity
- [x] 1.1 Review and update Stage 1 prompt to request concise responses
- [x] 1.2 Update Stage 2 evaluation prompt to encourage focused analysis
- [x] 1.3 Update Stage 3 synthesis prompt for concise final answers
- [x] 1.4 Add response length guidance in prompts (e.g., "Be concise, aim for 2-3 paragraphs")

## 2. Configuration Enhancements
- [x] 2.1 Add `max_tokens` configuration in `config.json` for each stage
- [x] 2.2 Add `response_style` setting in `config.json` (concise/standard)
- [x] 2.3 Implement token limit enforcement in `lmstudio.py` API calls

## 3. Integration with Streaming
- [x] 3.1 Ensure streaming (from add-streaming-deliberation) works with shorter responses
- [x] 3.2 Test combined effect of brevity + streaming on perceived responsiveness
- [x] 3.3 Add UI indication of response length mode if configurable
