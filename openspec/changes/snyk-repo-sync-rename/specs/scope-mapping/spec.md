## ADDED Requirements

### Requirement: Python 3.12 config module compatibility
The scope mapping configuration module MUST import successfully on Python 3.12 without runtime annotation evaluation errors. This MUST NOT rely on Python 3.14+ deferred annotation behavior.

#### Scenario: Worker starts on production container runtime
- **WHEN** the worker process starts in the production Docker image (Python 3.12)
- **THEN** `config.scope_mapping` imports successfully and `parse_scope_mapping` is callable before config file load
