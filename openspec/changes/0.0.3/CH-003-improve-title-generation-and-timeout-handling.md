# Change Proposal: Improve Title Generation and Timeout Handling

**Version:** 0.0.3
**Type:** Feature Enhancement + Bug Fix  
**Date:** 2025-01-26
**Status:** Proposed

> **Note:** Follow the versioning process outlined in `/AGENTS.md` for implementation and branch management.

## Summary

Improve the conversation title generation process to be more reliable and fix timeout issues that occur when LLM servers are busy. Title generation should be prioritized and block council member deliberation until complete, with proper exception handling and retry mechanisms.

## Current State

- Title generation runs in background after user submits message
- ReadTimeout exceptions occur frequently when LLM servers are busy
- No proper retry mechanism or timeout handling
- Title generation failures are silent or poorly handled
- Council members start deliberating immediately, potentially overwhelming the LLM server

## Proposed Changes

### 1. Sequential Title Generation
- Change title generation to run **before** council member deliberation
- Block council member queries until title is successfully generated
- This prevents overwhelming the LLM server with concurrent requests

### 2. Enhanced Timeout and Retry Handling
- Implement proper timeout configuration for different model types
- Add exponential backoff retry mechanism for failed requests
- Implement circuit breaker pattern for unresponsive models
- Add configurable timeout values in `config.json`

### 3. Improved Error Handling
- Catch and handle all timeout exceptions gracefully
- Provide detailed error logging with model-specific information
- Implement fallback strategies for title generation failures
- Add user-visible error states in the UI

### 4. Configuration Updates
Add new timeout and retry configuration to `config.json`:
```json
{
  "timeout_config": {
    "default_timeout": 30,
    "title_generation_timeout": 60,
    "max_retries": 3,
    "retry_backoff_factor": 2,
    "circuit_breaker_threshold": 5
  }
}
```

## Implementation Plan

### Backend Changes
1. **Title Generation Service** (`backend/title_generation.py`)
   - Create dedicated title generation service with proper async handling
   - Implement retry logic with exponential backoff
   - Add circuit breaker for unresponsive models

2. **LM Studio Integration** (`backend/lmstudio.py`)
   - Add configurable timeout handling
   - Implement proper exception catching for ReadTimeout
   - Add model-specific timeout configuration

3. **Main API** (`backend/main.py`)
   - Modify message submission flow to prioritize title generation
   - Ensure sequential execution: title → council deliberation
   - Add proper error propagation and user feedback

### Frontend Changes
1. **Title Display** (`frontend/src/components/ConversationList.vue`)
   - Add loading states for title generation
   - Show error states when title generation fails
   - Update title display immediately when generation completes

2. **Error Handling** (`frontend/src/stores/conversation.js`)
   - Add error handling for title generation failures
   - Implement retry UI for failed title generation

### Configuration Changes
1. **Timeout Configuration** (`config.json`)
   - Add timeout and retry configuration section
   - Make timeouts configurable per model type
   - Add circuit breaker settings

## Expected Benefits

1. **Reduced Timeouts**: Sequential processing prevents server overload
2. **Better Reliability**: Proper retry mechanisms handle temporary failures
3. **Improved UX**: Users see clear feedback about title generation status
4. **Better Error Recovery**: Graceful handling of server issues
5. **Configurable Behavior**: Admins can tune timeout/retry settings

## Testing Strategy

1. Test with busy LLM server scenarios
2. Verify title generation completes before council deliberation
3. Test timeout and retry mechanisms
4. Validate error handling and user feedback
5. Test with different model configurations

## Risks and Mitigation

**Risk**: Longer perceived response time due to sequential processing  
**Mitigation**: Improved user feedback and progress indicators

**Risk**: Title generation blocking entire conversation flow  
**Mitigation**: Fallback to default titles after max retries

## Dependencies

- Existing LLM server infrastructure
- Current conversation and title management system
- WebSocket infrastructure for real-time updates

## Rollback Plan

If issues occur:
1. Revert to parallel title generation
2. Restore original timeout handling
3. Remove new configuration parameters
4. Restore previous error handling behavior