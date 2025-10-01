# Python Development Instructions for Microsoft Agent Framework

## Overview

This document provides guidance for working with the Python implementation of the Microsoft Agent Framework. The Python implementation is located in the `python/` directory and follows modern Python conventions and best practices.

## Project Structure

```
python/
├── packages/                    # Python packages
│   ├── core/                    # Core agent framework
│   │   ├── agent_framework/     # Main package code
│   │   └── tests/               # Package-specific tests
│   ├── a2a/                     # Agent-to-Agent communication
│   ├── azure-ai/                # Azure AI integration
│   ├── copilotstudio/           # Copilot Studio integration
│   ├── devui/                   # Developer UI
│   ├── lab/                     # Experimental features (AF Labs)
│   ├── mem0/                    # mem0 integration
│   └── redis/                   # Redis integration
├── samples/                     # Sample applications
│   ├── getting_started/         # Getting started samples
│   │   ├── agents/              # Basic agent samples
│   │   ├── chat_client/         # Chat client samples
│   │   ├── workflows/           # Workflow samples
│   │   ├── middleware/          # Middleware samples
│   │   └── observability/       # Observability samples
│   └── semantic-kernel-migration/ # SK migration examples
├── tests/                       # Cross-package integration tests
├── docs/                        # Python-specific documentation
├── pyproject.toml               # Workspace configuration
├── uv.lock                      # Lock file for dependencies
├── DEV_SETUP.md                 # Development setup guide
└── README.md                    # Python-specific documentation
```

## Python Environment Setup

### Supported Versions

- **Python**: 3.10, 3.11, 3.12, 3.13
- **Target Version**: 3.10+ (code should be compatible with Python 3.10+)
- **OS**: Windows, macOS, Linux (including WSL)

### Tools

The project uses modern Python tooling:
- **uv**: Fast Python package manager and resolver (replaces pip/pip-tools)
- **poethepoet (poe)**: Task runner for automation
- **ruff**: Fast linter and formatter (replaces flake8, black, isort)
- **pytest**: Testing framework
- **pyright**: Static type checker (primary)
- **mypy**: Alternative type checker (secondary)

### Initial Setup

```bash
# Install uv (see DEV_SETUP.md for platform-specific instructions)
curl -LsSf https://astral.sh/uv/install.sh | sh  # Unix/macOS
# or
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# Install Python versions
uv python install 3.10 3.11 3.12 3.13

# Setup development environment (creates venv, installs deps, sets up pre-commit)
uv run poe setup -p 3.10  # or 3.11, 3.12, 3.13
```

## Package Architecture

### Monorepo Structure

The Python implementation uses a **monorepo** with multiple packages managed by `uv` workspaces:

1. **agent-framework-core**: Core functionality (agents, chat clients, tools, workflows)
2. **agent-framework-a2a**: Agent-to-Agent communication protocol
3. **agent-framework-azure-ai**: Azure AI integration
4. **agent-framework-copilotstudio**: Microsoft Copilot Studio integration
5. **agent-framework-mem0**: mem0 integration for memory management
6. **agent-framework-redis**: Redis integration for state management
7. **agent-framework-devui**: Developer UI for testing and debugging
8. **agent-framework-lab**: Experimental features and research

The **agent-framework** meta-package installs all sub-packages.

### Import Structure

Use flat imports from appropriate packages:

```python
# Core functionality
from agent_framework import ChatAgent, ChatMessage, ai_function

# Chat clients
from agent_framework.openai import OpenAIChatClient
from agent_framework.azure import AzureOpenAIChatClient

# Components
from agent_framework.workflows import Workflow, WorkflowNode
from agent_framework.vector_data import VectorStoreModel
from agent_framework.guardrails import ContentFilter

# Extensions
from agent_framework.azure_ai import AzureAIChatClient
from agent_framework.copilotstudio import CopilotStudioAgent
```

## Coding Standards

### Code Style and Formatting

The project uses **ruff** for both linting and formatting:

- **Line Length**: 120 characters
- **Target Python**: 3.10+
- **Style**: Google-style docstrings for all public functions, classes, and modules

Run formatting and linting:
```bash
# Format code
uv run poe fmt

# Lint and fix issues
uv run poe lint

# Run all checks (format, lint, type check, tests)
uv run poe check
```

### Type Annotations

- **All public APIs** must have type annotations
- Use modern type hints (`list[str]` not `List[str]` for Python 3.10+)
- Use `typing.Protocol` for structural typing
- Use `typing.Literal` for string enums when appropriate
- Use `| None` instead of `Optional` for unions with None

Example:
```python
from typing import Literal

def create_agent(
    name: str,
    instructions: str,
    tool_mode: Literal["auto", "required", "none"] | ChatToolMode = "auto"
) -> ChatAgent:
    """Create a chat agent."""
    ...
```

### Function Parameter Guidelines

- **Positional parameters**: Use only for up to 3 fully expected parameters
- **Keyword parameters**: Use for all other parameters, especially when there are multiple required parameters
- **String overrides**: Avoid requiring imports for common types by providing string alternatives
- **Document kwargs**: Always document how `**kwargs` are used
- **Separate kwargs**: Use specific parameters like `client_kwargs: dict[str, Any]` instead of mixing in `**kwargs`

Example:
```python
def create_client(
    *,  # Force keyword-only parameters
    api_key: str | None = None,
    endpoint: str | None = None,
    deployment_name: str | None = None,
    env_file_path: str | None = None,
    **client_kwargs: Any,
) -> ChatClient:
    """Create a chat client.
    
    Args:
        api_key: The API key for authentication.
        endpoint: The endpoint URL.
        deployment_name: The deployment name.
        env_file_path: Path to .env file with configuration.
        **client_kwargs: Additional keyword arguments passed to the underlying client.
    """
    ...
```

### Documentation

Follow Google-style docstrings:

```python
def equal(arg1: str, arg2: str) -> bool:
    """Compare two strings and return True if they are the same.

    This function performs a case-sensitive comparison of two strings.

    Args:
        arg1: The first string to compare.
        arg2: The second string to compare.

    Returns:
        True if the strings are identical, False otherwise.

    Raises:
        ValueError: If either string is empty.
    """
    if not arg1 or not arg2:
        raise ValueError("Strings cannot be empty")
    return arg1 == arg2
```

Documentation sections (in order):
1. Single-line summary (ending with period)
2. Extended description (optional, after blank line)
3. `Args:` - Parameter descriptions
4. `Returns:` or `Yields:` - Return value description
5. `Raises:` - Exception descriptions

Private functions (starting with `_`) don't require docstrings but can have them for clarity.

### Asynchronous Programming

Most of the library is **async-first**:

- Use `async def` for I/O operations
- Always `await` async functions
- Never block on async code with `.result()` or `asyncio.run()` in library code
- Provide sync wrappers only when necessary
- Use `asyncio.run()` only in scripts/examples

Example:
```python
async def run_agent(agent: ChatAgent, prompt: str) -> str:
    """Run an agent asynchronously."""
    result = await agent.run(prompt)
    return result

# In scripts/samples
if __name__ == "__main__":
    asyncio.run(main())
```

### Logging

Use the centralized logging system:

```python
from agent_framework import get_logger

# For main package
logger = get_logger()

# For subpackages
logger = get_logger("agent_framework.azure")

# Usage
logger.info("Agent {agent_name} processing request", agent_name=agent_name)
logger.debug("Received response: {response}", response=response)
logger.error("Error occurred: {error}", error=str(error), exc_info=True)
```

**Do not use** direct logging imports:
```python
# ❌ Avoid this
import logging
logger = logging.getLogger(__name__)
```

### Pydantic Models

The framework uses Pydantic for serialization:

```python
from pydantic import Field
from agent_framework._pydantic import AFBaseModel

class MyConfig(AFBaseModel):
    """Configuration for my feature."""
    name: str
    value: int = Field(default=0, description="The value to use")
    options: dict[str, str] = Field(default_factory=dict)
```

For generic types:
```python
from typing import Generic, TypeVar
from agent_framework._pydantic import AFBaseModel

T = TypeVar("T")

class Container(AFBaseModel, Generic[T]):
    """A generic container."""
    item: T
```

## Testing

### Test Organization

- **Unit tests**: In `tests/` directory within each package
- **Integration tests**: Require external services (OpenAI, Azure, etc.)
- **Sample tests**: Ensure samples remain functional (in `tests/samples/`)

### Running Tests

```bash
# Run all tests with coverage
uv run poe test

# Run tests for specific package
uv run poe --directory packages/core test

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_agents.py

# Run specific test
uv run pytest tests/test_agents.py::test_create_agent
```

### Integration Tests

Integration tests are marked with decorators and only run when enabled:

```python
from tests.utils import skip_if_openai_integration_tests_disabled

@skip_if_openai_integration_tests_disabled
async def test_openai_integration():
    """Test OpenAI integration."""
    # Test code that calls OpenAI API
```

To run integration tests:
```bash
# Set environment variable
export RUN_INTEGRATION_TESTS=true

# Run tests
uv run poe test
```

### Test Structure

```python
import pytest
from agent_framework import ChatAgent

class TestChatAgent:
    """Tests for ChatAgent class."""
    
    def test_create_agent(self):
        """Test creating a basic agent."""
        agent = ChatAgent(name="TestAgent")
        assert agent.name == "TestAgent"
    
    @pytest.mark.asyncio
    async def test_run_agent(self, mock_chat_client):
        """Test running an agent."""
        agent = ChatAgent(chat_client=mock_chat_client)
        result = await agent.run("Hello")
        assert result is not None
```

### Test Coverage

- Target: **Minimum 80% coverage** for all packages
- Coverage reports generated automatically during test runs
- Use `uv run poe test` to see coverage report

## Configuration Management

### Environment Variables

Use environment variables or `.env` files for configuration:

```python
# .env file
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL_ID=gpt-4o-mini
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
```

Load configuration:
```python
from agent_framework.openai import OpenAIChatClient

# Automatically loads from environment or .env file
client = OpenAIChatClient()

# Or specify custom .env file
client = OpenAIChatClient(env_file_path="custom.env")

# Or pass directly
client = OpenAIChatClient(
    api_key="sk-...",
    model_id="gpt-4o-mini"
)
```

**Never commit** `.env` files or hardcode secrets!

## Common Development Tasks

### Adding a New Package

1. Create package directory in `packages/`
2. Add `pyproject.toml` with package metadata
3. Create package structure:
   ```
   packages/my_package/
   ├── pyproject.toml
   ├── agent_framework_my_package/
   │   ├── __init__.py
   │   └── my_module.py
   └── tests/
       └── test_my_module.py
   ```
4. Add to workspace in root `pyproject.toml`
5. Add to `[tool.uv.sources]` section
6. Update documentation

### Adding a New Feature

1. Design the API (consider consistency with .NET implementation)
2. Add type-annotated interfaces/protocols
3. Implement the feature
4. Add comprehensive docstrings
5. Write unit tests
6. Add integration tests if applicable
7. Create sample demonstrating the feature
8. Update README and documentation

### Creating a Sample

Samples should be:
- Self-contained and runnable
- Well-documented with comments
- Include environment setup instructions
- Use `.env.example` for required configuration
- Follow the project coding standards

Example structure:
```python
"""Sample: Basic agent with tools.

This sample demonstrates how to create an agent with custom tools.
"""

import asyncio
from typing import Annotated
from pydantic import Field
from agent_framework import ChatAgent, ai_function
from agent_framework.openai import OpenAIChatClient


@ai_function
def get_weather(
    location: Annotated[str, Field(description="The city name")]
) -> str:
    """Get the current weather for a location."""
    return f"The weather in {location} is sunny."


async def main():
    """Run the sample."""
    agent = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="WeatherBot",
        instructions="You help users with weather information.",
        tools=[get_weather]
    )
    
    result = await agent.run("What's the weather in Seattle?")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

## Available Poe Tasks

Quick reference for common tasks:

```bash
# Setup
uv run poe setup                    # Full setup with venv and pre-commit
uv run poe install                  # Install/update dependencies

# Code Quality
uv run poe fmt                      # Format code with ruff
uv run poe lint                     # Lint and fix issues
uv run poe pyright                  # Type check with pyright
uv run poe mypy                     # Type check with mypy
uv run poe check                    # Run all checks (fmt, lint, pyright, mypy, test)

# Testing
uv run poe test                     # Run tests with coverage

# Documentation
uv run poe docs-build               # Build documentation
uv run poe docs-full                # Full docs rebuild
uv run poe docs-debug               # Build docs with debug info

# Validation
uv run poe markdown-code-lint       # Lint markdown code blocks
uv run poe samples-code-check       # Type check samples

# Building
uv run poe build                    # Build packages
```

## Pre-commit Hooks

Pre-commit hooks automatically run checks before commits:

```bash
# Install hooks (done by poe setup)
uv run poe pre-commit-install

# Run manually
uv run pre-commit run -a

# Update hooks
pre-commit autoupdate
```

Hooks include:
- Code formatting (ruff)
- Linting (ruff)
- Type checking (pyright)
- Trailing whitespace removal
- YAML/JSON validation

## Common Patterns

### Creating an Agent

```python
import asyncio
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient


async def main():
    agent = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="MyAgent",
        instructions="You are a helpful assistant."
    )
    
    result = await agent.run("Hello!")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

### Adding Tools

```python
from typing import Annotated
from pydantic import Field
from agent_framework import ChatAgent, ai_function


@ai_function
def calculate(
    operation: Annotated[str, Field(description="The operation: add, subtract, multiply, divide")],
    a: Annotated[float, Field(description="First number")],
    b: Annotated[float, Field(description="Second number")]
) -> float:
    """Perform a calculation."""
    operations = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else float('nan')
    }
    return operations[operation](a, b)


agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    tools=[calculate]
)
```

### Using Middleware

```python
from agent_framework import ChatAgent
from agent_framework.middleware import MiddlewareContext


async def logging_middleware(context: MiddlewareContext, next):
    """Log requests and responses."""
    print(f"Request: {context.request}")
    await next()
    print(f"Response: {context.response}")


agent = ChatAgent(chat_client=OpenAIChatClient())
agent.add_middleware(logging_middleware)
```

### Workflows

```python
from agent_framework.workflows import Workflow, WorkflowBuilder


async def main():
    researcher = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Researcher",
        instructions="You research topics thoroughly."
    )
    
    writer = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Writer",
        instructions="You write clear, engaging content."
    )
    
    workflow = WorkflowBuilder()\
        .add_agent("researcher", researcher)\
        .add_agent("writer", writer)\
        .connect("researcher", "writer")\
        .build()
    
    result = await workflow.run("Research and write about AI agents")
    print(result)
```

## Performance Considerations

- Use `asyncio` for I/O-bound operations
- Avoid blocking operations in async code
- Use streaming for large responses
- Consider connection pooling for HTTP clients
- Profile before optimizing (`cProfile`, `line_profiler`)

## Debugging

### VSCode Setup

1. Open the `python/` folder as workspace root
2. Select interpreter from `.venv` (created by uv)
3. Use the Python extension for debugging
4. Set breakpoints and use F5 to debug

### Logging

Set log level via environment:
```bash
export LOG_LEVEL=DEBUG
python sample.py
```

Or in code:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### OpenTelemetry

For distributed tracing:
```python
from agent_framework.observability import setup_telemetry

setup_telemetry(service_name="my-agent")
```

See `samples/getting_started/observability/` for examples.

## Additional Resources

- **DEV_SETUP.md**: Detailed development setup guide
- **Python Samples**: Browse `samples/getting_started/` for comprehensive examples
- **Design Docs**: See `docs/design/` for technical specifications
- **ADRs**: Review `docs/decisions/` for architectural decisions (especially `0005-python-naming-conventions.md`)
- **Package Docs**: Each package has its own README in `packages/*/`

## Getting Help

- Check existing samples first
- Review test cases for usage examples
- Read `DEV_SETUP.md` for environment issues
- File GitHub issues for bugs
- Use GitHub Discussions for questions
- Join the Microsoft Azure AI Foundry Discord
