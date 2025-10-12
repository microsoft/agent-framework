# Python Implementation Domain

## Purpose
Navigation hub for all Python-specific documentation, architecture, and implementation details.

## Classification
- **Domain:** Python
- **Stability:** Semi-stable
- **Abstraction:** Structural
- **Confidence:** Established

## Overview

The Python implementation of Microsoft Agent Framework is located in `python/` and provides a complete agent framework with async-first design and tier-based imports.

## Package Structure

### Core Package: `agent-framework-core`

**Import Tiers**:

- **Tier 0 (Core)**: Direct import from `agent_framework`
  ```python
  from agent_framework import ChatAgent, ai_function, get_logger
  ```

- **Tier 1 (Components)**: Import from `agent_framework.<component>`
  ```python
  from agent_framework.vector_data import VectorStoreModel
  from agent_framework.workflows import Workflow
  from agent_framework.guardrails import ContentFilter
  from agent_framework.observability import configure_tracing
  ```

- **Tier 2 (Connectors)**: Import from `agent_framework.<vendor>`
  ```python
  from agent_framework.openai import OpenAIChatClient
  from agent_framework.azure import AzureOpenAIChatClient
  from agent_framework.anthropic import AnthropicChatClient
  ```

### Extension Packages

Independently versioned packages:
- `agent-framework-a2a`: Agent-to-Agent communication
- `agent-framework-azure-ai`: Azure AI integration
- `agent-framework-copilotstudio`: Copilot Studio agents
- `agent-framework-devui`: Developer UI
- `agent-framework-lab`: Experimental features
- `agent-framework-mem0`: Memory integration
- `agent-framework-redis`: Redis integration

## Key Architectural Patterns

### Async-First Design
All I/O operations use `async def`. Always assume asynchronous unless signature indicates otherwise.

### Lazy Loading
Subpackages use lazy imports to avoid loading entire packages when importing single components. Missing dependencies raise meaningful errors indicating which extra to install.

### Namespace Packages
Independent packages can be installed separately:
```bash
pip install agent-framework[google]  # Install with Google connectors
pip install agent-framework-google   # Or install connector directly
```

### Protocol-Based Abstractions
Chat client protocol provides consistent interface across LLM providers.

### Composition Over Inheritance
Prefer attributes over subclassing:
```python
# ✅ Preferred
ChatMessage(role="user", content="Hello")

# ❌ Avoid
UserMessage(content="Hello")
```

## Development Setup

See [Development Processes](../../processes/development.md#python-development) for complete setup instructions.

Quick start:
```bash
cd python/
uv run poe setup -p 3.13
```

## Code Quality Standards

- **Formatter**: Ruff (120 character line length)
- **Type Checking**: Pyright strict mode, Mypy strict
- **Docstrings**: Google-style required for public APIs
- **Target**: Python 3.10+
- **Coverage**: 80%+ type coverage target

See [Development Principles](../../foundation/principles.md#python-standards) for complete standards.

## Testing

```bash
# All tests with coverage
uv run poe test

# Single package tests
uv run poe --directory packages/core test

# Integration tests (requires environment variables)
RUN_INTEGRATION_TESTS=true uv run pytest
```

## Key Implementation Areas

### Agents
- Single agents (`ChatAgent`)
- Agent threads
- Tool calling
- Memory and context

### Tools
- Function decorators (`@ai_function`)
- MCP integration
- OpenAPI tool generation
- Custom tool protocols

### Workflows
- Graph-based orchestration
- Conditional routing
- Concurrent execution
- Checkpointing and state management

### Observability
- OpenTelemetry integration
- Centralized logging (`get_logger()`)
- Telemetry and metrics

## Related Documentation

### Foundation
- [Project Definition](../../foundation/project_definition.md)
- [Architecture Overview](../../foundation/architecture.md)
- [Development Principles](../../foundation/principles.md)

### Processes
- [Development Setup](../../processes/development.md)
- [Contributing](../../processes/contributing.md)

### Decisions
- [0005: Python Naming Conventions](../../decisions/0005-python-naming-conventions.md)
- [0007: Python Subpackages](../../decisions/0007-python-subpackages.md)

### Design
- [Python Package Setup](../../design/python-package-setup.md)

## Navigation Paths

### For New Contributors
1. Start: [Development Setup](../../processes/development.md#python-development)
2. Understand: [Development Principles](../../foundation/principles.md#python-standards)
3. Code: Follow naming conventions and patterns

### For Feature Implementation
1. Review: [Architecture Overview](../../foundation/architecture.md)
2. Check: [Relevant ADRs](../../decisions/index.md)
3. Design: Create design document if complex
4. Implement: Follow code quality standards
5. Test: Write tests with good coverage

### For Bug Fixes
1. Reproduce: Write failing test
2. Fix: Implement solution
3. Verify: Run quality checks (`uv run poe check`)
4. Submit: Create PR with test and fix

## Relationship Network
- **Prerequisite Information**:
  - [Project Definition](../../foundation/project_definition.md)
  - [Architecture Overview](../../foundation/architecture.md)
- **Related Information**:
  - [.NET Domain](../dotnet/index.md)
  - [Workflows Domain](../workflows/index.md)
- **Implementation Details**:
  - Python package documentation: `python/packages/*/README.md`
  - Sample code: `python/samples/`

## Metadata
- **Created:** 2025-10-11
- **Last Updated:** 2025-10-11
- **Updated By:** Context Network Setup

## Change History
- 2025-10-11: Initial domain index created during context network setup
