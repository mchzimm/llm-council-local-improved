# Change 026: Fix Tool Result Context in Prompts

## Summary
Fix issue where council models claim "lack access to current information" despite having tool results with real-time data.

## Problem
When a websearch or other real-time tool is executed successfully:
1. The tool result is correctly passed to council models
2. However, models' internal reasoning still says "I don't have live news access" 
3. This causes them to refuse answering or provide outdated information
4. Example: "I cannot provide news for November 27, 2025 (a future date)"

## Root Cause
The prompts that include tool results don't strongly enough convey:
- That the tool output contains **current, real-time data**
- That models should **trust** the tool output as authoritative
- The actual current date/time to establish temporal context

## Solution
Update prompts in both:
1. `chairman_direct_response()` - for direct factual responses
2. `stage1_collect_responses_streaming()` - for council deliberation

New prompt structure:
```
IMPORTANT CONTEXT:
- Today's date: [current date] | Current time: [current time]
- A real-time tool was executed to fetch CURRENT, LIVE data for this query
- The tool output below contains UP-TO-DATE information retrieved just now
- DO NOT claim you "lack access to current information" - you HAVE it via the tool output

[tool_context]

Question: [user_query]

Instructions:
1. The tool output above is CURRENT and AUTHORITATIVE - use it directly
2. Present the information as current facts (because they ARE current)
3. [additional style instructions]
```

## Files Changed
- `backend/council.py`: Updated prompts in two functions

## Testing
1. Start the application: `./start.sh`
2. Ask: "What are today's top 5 news?"
3. Verify:
   - Websearch tool executes (tool card appears)
   - Models use the tool output directly
   - No "I cannot access current information" responses
   - News is presented as current facts

## Version
0.1.10
