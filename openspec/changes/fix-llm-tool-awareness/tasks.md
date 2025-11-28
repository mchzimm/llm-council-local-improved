## 1. Implementation

- [x] 1.1 Strengthen system prompts to override training cutoff concerns
  - Add explicit statement that current year IS 2025
  - Add "DO NOT claim you lack access" instruction
  - Emphasize tool output is real, live data
  
- [x] 1.2 Add refusal detection and retry logic
  - Detect phrases like "cannot access", "lack real-time", "training cutoff"
  - If detected, retry with even stronger prompt override
  
- [x] 1.3 Improve tool result formatting to be more explicit
  - Add "LIVE DATA FROM [timestamp]" header
  - Make it clear this is not simulated/hypothetical data
  
- [x] 1.4 Run automated tests to verify fix
- [x] 1.5 Iterate on failures until tests pass
