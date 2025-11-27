# Change: Conversation Title Tooltip on Hover

## Why
Long conversation titles get truncated in the sidebar. Users need a way to see the full title without clicking into the conversation.

## What Changes
- Add cursor tooltip showing full conversation title on hover over conversation item in sidebar
- Tooltip displays complete title text when title is truncated

## Impact
- Affected specs: conversation-ui (new)
- Affected code: `frontend/src/components/Sidebar.jsx`, `frontend/src/components/Sidebar.css`
