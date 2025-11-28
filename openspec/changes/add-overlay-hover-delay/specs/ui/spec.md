## ADDED Requirements

### Requirement: Overlay Group Hover Delay
The system SHALL delay closing overlays by 2 seconds when the cursor leaves an overlay group, allowing users to navigate between related overlays without them closing prematurely.

#### Scenario: Cursor moves between overlays in same group
- **WHEN** cursor leaves the MCP server overlay but enters the tools overlay within 2 seconds
- **THEN** neither overlay closes

#### Scenario: Cursor leaves entire overlay group
- **WHEN** cursor leaves all overlays in the group and does not re-enter within 2 seconds
- **THEN** all overlays in the group close

#### Scenario: Cursor re-enters overlay group during delay
- **WHEN** cursor leaves overlay group but re-enters before 2 seconds elapsed
- **THEN** the close timer is cancelled and overlays remain open
