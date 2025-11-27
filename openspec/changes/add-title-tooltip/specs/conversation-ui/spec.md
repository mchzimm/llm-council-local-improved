## ADDED Requirements

### Requirement: Conversation Title Tooltip
The system SHALL display the full conversation title as a cursor tooltip when the user hovers over a conversation item in the sidebar.

#### Scenario: Truncated title hover
- **WHEN** user hovers over a conversation item with a truncated title
- **THEN** a tooltip displays the full conversation title text

#### Scenario: Non-truncated title hover
- **WHEN** user hovers over a conversation item with a non-truncated title
- **THEN** a tooltip still displays the conversation title for consistency
