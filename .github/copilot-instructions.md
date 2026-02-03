# GitHub Copilot Instructions

Microsoft Agent Framework - a multi-language framework for building, orchestrating, and deploying AI agents.

## Repository Structure

- `python/` - Python implementation (packages in `python/packages/`, samples in `python/samples/`)
- `dotnet/` - C#/.NET implementation (source in `dotnet/src/`, samples in `dotnet/samples/`)
- `docs/` - Design documents and architectural decision records

## Build, Test, and Lint Commands

### Python

```bash
# From python/ directory
uv run poe check          # Run all checks (format, lint, type check, test)
uv run poe fmt            # Format code with ruff
uv run poe lint           # Lint with ruff
uv run poe pyright        # Type check with pyright
uv run poe test           # Run all tests with coverage

# Run tests for a specific package
uv run --directory packages/core poe test

# Run a single test file
uv run pytest packages/core/tests/test_agents.py

# Run a single test
uv run pytest packages/core/tests/test_agents.py::test_function_name -v
```

### .NET

```bash
# From dotnet/ directory
dotnet build              # Build all projects
dotnet test               # Run all tests
dotnet format             # Auto-fix formatting

# Run a single test
dotnet test --filter "FullyQualifiedName~TestClassName.TestMethodName"
```

## Architecture

### Python Package Structure

The Python codebase uses a monorepo with lazy-loaded connector packages:

- `agent-framework-core` - Core abstractions (`ChatAgent`, `ChatMessage`, tool definitions, workflows)
- `agent-framework-<provider>` - Provider-specific packages (azure-ai, anthropic, ollama, etc.)

Users import from a unified namespace:
```python
from agent_framework import ChatAgent, tool
from agent_framework.openai import OpenAIChatClient
from agent_framework.azure import AzureOpenAIChatClient
```

Provider folders in core use `__getattr__` for lazy loading - classes are only imported when accessed.

### .NET Package Structure

- `Microsoft.Agents.AI` - Core AI agent abstractions
- `Microsoft.Agents.AI.<Provider>` - Provider implementations (OpenAI, AzureAI, Anthropic, etc.)
- `Microsoft.Agents.AI.Workflows` - Workflow orchestration
- `Microsoft.Extensions.AI.Agents` - Integration with Microsoft.Extensions.AI

## Key Conventions

### Python

- **Copyright header**: `# Copyright (c) Microsoft. All rights reserved.` at top of all `.py` files
- **Type hints**: Always specify return types and parameter types; use `Type | None` instead of `Optional`
- **Logging**: Use `from agent_framework import get_logger` (not `import logging`)
- **Docstrings**: Google-style for all public functions/classes
- **Line length**: 120 characters
- **Async**: Assume async by default; check function signatures
- **Tests**: Do not mark with `@pytest.mark.asyncio` (auto mode enabled)
- **Keyword args**: Use for functions with >3 parameters; document `**kwargs` usage

### .NET

- **Copyright header**: `// Copyright (c) Microsoft. All rights reserved.` at top of all `.cs` files
- **XML docs**: Required for all public methods and classes
- **Async**: Use `Async` suffix for methods returning `Task`/`ValueTask`
- **Private classes**: Should be `sealed` unless subclassed
- **Config**: Read from environment variables with `UPPER_SNAKE_CASE` naming
- **Tests**: Use `this.` for class members; add Arrange/Act/Assert comments; use Moq for mocking

### Samples

Both Python and .NET samples follow similar patterns:
1. Copyright header
2. Imports/usings
3. Description comment
4. Main code logic
5. Helper methods at bottom

Configuration via environment variables (never hardcode secrets). Keep samples simple and focused.
