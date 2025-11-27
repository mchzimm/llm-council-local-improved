## ADDED Requirements

### Requirement: Concise Response Generation
The system SHALL configure LLM prompts to encourage concise, focused responses to reduce generation time and improve perceived responsiveness.

#### Scenario: Stage 1 concise response
- **WHEN** a council model generates a Stage 1 response
- **THEN** the response is focused and avoids unnecessary verbosity

#### Scenario: Stage 2 concise evaluation
- **WHEN** a council model evaluates peer responses in Stage 2
- **THEN** the evaluation provides key insights without excessive detail

### Requirement: Response Length Configuration
The system SHALL support configurable maximum token limits for LLM responses.

#### Scenario: Token limit enforced
- **WHEN** a model reaches the configured max_tokens limit
- **THEN** the response is truncated at that limit

#### Scenario: Model-specific token limits
- **WHEN** different models have different max_tokens configured
- **THEN** each model respects its individual token limit

### Requirement: Combined Streaming and Brevity
The system SHALL combine token streaming with shorter responses to minimize time-to-first-token and total response time.

#### Scenario: Fast first token with brief response
- **WHEN** user submits a query
- **THEN** first response tokens appear within seconds and complete response arrives quickly due to brevity constraints
