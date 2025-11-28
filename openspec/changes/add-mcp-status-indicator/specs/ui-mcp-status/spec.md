## ADDED Requirements

### Requirement: MCP Status Badge Display
The system SHALL display an "MCP" badge next to the "LLM Council" title in the sidebar header.

#### Scenario: Badge appears on load
- **WHEN** the application loads
- **THEN** "MCP" text appears next to "LLM Council" title
- **AND** the text is styled blue, bold, with light grey edge
- **AND** the text size matches the title size

### Requirement: Server Status Overlay
The system SHALL display a semi-transparent overlay with MCP server status when hovering the header title area.

#### Scenario: Hover shows server list
- **WHEN** user hovers over the "LLM Council MCP" title area
- **THEN** a dark semi-transparent overlay (20% transparency) appears
- **AND** the overlay auto-sizes to fit content
- **AND** each MCP server is listed with a status indicator

#### Scenario: Status indicators show correct state
- **WHEN** a server is available and idle
- **THEN** a green indicator is shown
- **WHEN** a server is processing a tool call
- **THEN** a yellow indicator is shown
- **WHEN** a server is offline or unreachable
- **THEN** a red indicator is shown

#### Scenario: Server metrics displayed
- **WHEN** the server overlay is visible
- **THEN** metrics are shown below the server list
- **AND** metrics include total server count and available tools count

### Requirement: Tool Status Overlay
The system SHALL display a secondary overlay showing server tools when hovering a server in the status overlay.

#### Scenario: Server hover shows tools
- **WHEN** user hovers over a server entry in the status overlay
- **THEN** a secondary overlay appears listing all tools for that server
- **AND** tool names are displayed in default text color

#### Scenario: Active tools highlighted
- **WHEN** a tool is currently being used
- **THEN** the tool's text color changes to medium yellow
- **AND** updates in real-time as tool status changes

#### Scenario: Tool metrics displayed
- **WHEN** the tool overlay is visible
- **THEN** metrics are shown below the tool list
- **AND** metrics include total tool count and active tool count
