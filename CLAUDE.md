# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Microsoft Agent Framework is a multi-language framework for building, orchestrating, and deploying AI agents with support for both .NET and Python. The repository contains:

- **Python implementation**: `python/` - Core framework and extension packages
- **.NET implementation**: `dotnet/` - C# implementation with similar capabilities
- **Workflow samples**: `workflow-samples/` - Cross-platform workflow examples
- **Documentation**: `docs/` - Design documents and architectural decision records

## Development Commands

### Python Development

**Prerequisites**: Install `uv` (see `python/DEV_SETUP.md`):
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS (Homebrew)
brew install uv
```

**Setup** (from `python/` directory):
```bash
# Initial setup with Python 3.10-3.13
uv run poe setup -p 3.13

# Or manually:
uv python install 3.10 3.11 3.12 3.13
uv venv --python 3.13
uv sync --dev
uv run poe install
uv run poe pre-commit-install
```

**Common Development Tasks**:
```bash
# Format code (ruff)
uv run poe fmt

# Run linting
uv run poe lint

# Run type checking (pyright and mypy)
uv run poe pyright
uv run poe mypy

# Run tests with coverage
uv run poe test

# Run all quality checks (format, lint, pyright, mypy, test, markdown lint, samples check)
uv run poe check

# Run pre-commit checks (excludes mypy)
uv run poe pre-commit-check
```

**Running Tests**:
```bash
# All tests with coverage
uv run poe test

# Single package tests (from python/ directory)
uv run poe --directory packages/core test

# Single test file (from python/ directory)
uv run pytest tests/test_agents.py

# Verbose output
uv run pytest -v

# Integration tests (requires RUN_INTEGRATION_TESTS=true in env)
RUN_INTEGRATION_TESTS=true uv run pytest
```

**Documentation**:
```bash
# Build documentation
uv run poe docs-build

# Serve locally with auto-reload
uv run poe docs-serve

# Full rebuild (clean + build + rename)
uv run poe docs-rebuild
```

### .NET Development

**Build** (from `dotnet/` directory):
```bash
dotnet build
```

**Run Tests**:
```bash
dotnet test
```

**Linting (auto-fix)**:
```bash
dotnet format
```

## Architecture

### Python Package Structure

The Python implementation follows a **flat import structure** with three tiers:

**Tier 0 (Core)** - Import from `agent_framework`:
- Agents (single agents, threads)
- Tools (includes MCP and OpenAPI)
- Types/Models
- Logging
- Middleware
- Telemetry

Example:
```python
from agent_framework import ChatAgent, ai_function
```

**Tier 1 (Advanced Components)** - Import from `agent_framework.<component>`:
- `vector_data` - Vector stores
- `guardrails` - Content filters
- `workflows` - Multi-agent orchestration
- `observability` - OpenTelemetry integration

Example:
```python
from agent_framework.vector_data import VectorStoreModel
from agent_framework.workflows import Workflow
```

**Tier 2 (Connectors)** - Import from `agent_framework.<vendor>`:
- `openai` - OpenAI chat clients, tools
- `azure` - Azure OpenAI integration
- `copilotstudio` - Copilot Studio agents
- `a2a` - Agent-to-Agent communication
- `mem0` - Memory integration
- `redis` - Redis integration

Example:
```python
from agent_framework.openai import OpenAIChatClient
from agent_framework.azure import AzureOpenAIChatClient
```

**Package Organization**:
```
python/
├── packages/
│   ├── core/              # agent-framework-core (main package)
│   │   └── agent_framework/
│   ├── a2a/               # agent-framework-a2a
│   ├── azure-ai/          # agent-framework-azure-ai
│   ├── copilotstudio/     # agent-framework-copilotstudio
│   ├── devui/             # agent-framework-devui (developer UI)
│   ├── lab/               # agent-framework-lab (experimental features)
│   ├── mem0/              # agent-framework-mem0
│   └── redis/             # agent-framework-redis
├── samples/               # Sample applications
│   └── getting_started/
│       ├── agents/
│       ├── chat_client/
│       ├── workflows/
│       ├── middleware/
│       ├── tools/
│       └── observability/
├── tests/                 # Tests (located in each package)
├── pyproject.toml         # Workspace configuration
└── DEV_SETUP.md          # Development setup guide
```

All subpackages use namespace packages allowing independent versioning and dependencies.

### .NET Package Structure

```
dotnet/
├── src/
│   ├── Microsoft.Agents.AI/                    # Core agent functionality
│   ├── Microsoft.Agents.AI.Abstractions/       # Core abstractions
│   ├── Microsoft.Agents.AI.OpenAI/            # OpenAI integration
│   ├── Microsoft.Agents.AI.AzureAI/           # Azure AI integration
│   ├── Microsoft.Agents.AI.A2A/               # Agent-to-Agent
│   ├── Microsoft.Agents.AI.CopilotStudio/     # Copilot Studio
│   ├── Microsoft.Agents.AI.Workflows/         # Workflow engine
│   ├── Microsoft.Agents.AI.Workflows.Declarative/
│   ├── Microsoft.Agents.AI.Hosting/           # Hosting abstractions
│   ├── Microsoft.Agents.AI.Hosting.A2A/
│   ├── Microsoft.Agents.AI.Hosting.A2A.AspNetCore/
│   └── Microsoft.Agents.AI.Hosting.OpenAI/
├── samples/
│   └── GettingStarted/
│       ├── Agents/
│       ├── AgentProviders/
│       ├── Workflows/         # Extensive workflow samples
│       ├── AgentOpenTelemetry/
│       └── ModelContextProtocol/
└── tests/
```

### Workflow Architecture

Both Python and .NET support **graph-based workflows** with:

- **Executors**: Nodes in the workflow graph (agents or functions)
- **Edges**: Data flows between executors (static or conditional)
- **Streaming**: Real-time event streaming from workflow execution
- **Checkpointing**: Save/restore workflow state for time-travel debugging
- **Human-in-the-Loop**: External interactions via input ports
- **Concurrent Execution**: Fan-out/fan-in patterns for parallel processing
- **Shared States**: Data sharing between executors

Key workflow patterns (see `.NET samples/GettingStarted/Workflows/`):
- Sequential orchestration
- Concurrent/parallel execution
- Conditional routing (edge conditions, switch-case, multi-selection)
- Looping
- Agent handoffs
- Multi-service coordination

**Declarative workflows**: Can be defined in YAML (see `workflow-samples/`)

### Key Design Patterns

**Asynchronous-First**: Most of the Python library uses `async def`. Always assume asynchronous operations unless signature indicates otherwise.

**Lazy Loading**: Subpackages use lazy imports to avoid loading entire packages when importing single components. Missing dependencies raise meaningful errors indicating which extra to install.

**Namespace Packages**: Python connectors are independent packages that can be installed separately:
```bash
pip install agent-framework[google]  # Install with Google connectors
pip install agent-framework-google   # Or install connector directly
```

**Chat Client Protocol**: Both languages implement a consistent chat client protocol for different LLM providers (OpenAI, Azure OpenAI, Azure AI, Copilot Studio).

## Code Quality Standards

### Python

**Formatting & Linting**: Uses `ruff` with:
- Line length: 120 characters
- Target: Python 3.10+
- Google-style docstrings required for all public functions/classes/modules

**Type Checking**:
- `pyright` in strict mode
- `mypy` with strict settings
- Target coverage: 80%+ for all packages

**Function Parameters**:
- Use positional parameters only for up to 3 fully expected parameters
- Use keyword parameters for all other parameters
- Avoid requiring additional imports (provide string-based overrides)
- Document kwargs with references or explanations
- Separate kwargs by purpose (e.g., `client_kwargs: dict[str, Any]`)

**Docstrings** (Google style):
```python
def create_agent(name: str, chat_client: ChatClientProtocol) -> Agent:
    """Create a new agent with the specified configuration.

    Additional explanation if needed (optional).

    Args:
        name: The name of the agent.
        chat_client: The chat client to use for communication.

    Returns:
        A configured Agent instance.

    Raises:
        ValueError: If name is empty.
    """
```

**Logging**: Use centralized logging, not direct imports:
```python
# ✅ Correct
from agent_framework import get_logger
logger = get_logger()  # or get_logger('agent_framework.azure')

# ❌ Incorrect
import logging
logger = logging.getLogger(__name__)
```

**Prefer Attributes Over Inheritance**:
```python
# ✅ Preferred
ChatMessage(role="user", content="Hello")
ChatMessage(role="assistant", content="Hi")

# ❌ Avoid
UserMessage(content="Hello")
AssistantMessage(content="Hi")
```

### .NET

- Follow [.NET coding conventions](https://learn.microsoft.com/dotnet/csharp/fundamentals/coding-style/coding-conventions)
- Use `dotnet format` for consistent formatting
- Include tests for new features and bug fixes

## Testing

### Python Integration Tests

Integration tests are marked with `@skip_if_..._integration_tests_disabled` decorators. To run:

```bash
# Set environment variable
export RUN_INTEGRATION_TESTS=true

# Also requires service-specific keys (OpenAI, Azure OpenAI, etc.)
# Set in .env file or environment variables:
export OPENAI_API_KEY="..."
export AZURE_OPENAI_ENDPOINT="..."
export AZURE_OPENAI_API_KEY="..."
```

Test markers:
- `@pytest.mark.azure` - Azure provider tests
- `@pytest.mark.azure-ai` - Azure AI provider tests
- `@pytest.mark.openai` - OpenAI provider tests

### Test Coverage

Run tests with coverage reports:
```bash
# Python
uv run poe test  # Shows coverage report with uncovered lines

# .NET
dotnet test /p:CollectCoverage=true
```

## Contributing

1. **File an issue** for non-trivial changes before starting work
2. **Create a branch** off `main` with descriptive name (e.g., `issue-123` or `feature-name`)
3. **Add tests** for new features or bug fixes
4. **Run quality checks** before committing:
   - Python: `uv run poe check`
   - .NET: `dotnet build && dotnet test && dotnet format`
5. **Create PR** against `main` branch
6. **Pre-commit hooks**: Automatically installed with `uv run poe setup`

**DO**:
- Follow existing code style and conventions
- Include tests with new features
- Use pre-commit hooks for Python

**DON'T**:
- Surprise with large PRs (discuss first in an issue)
- Submit PRs that alter licensing files
- Make new APIs without discussion

## Environment Setup

### Python API Keys

Create `.env` file in `python/` directory:
```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL_ID=gpt-4o-mini

# Azure OpenAI
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://....openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=...
AZURE_OPENAI_API_VERSION=2024-08-01-preview

# Azure AI
AZURE_AI_PROJECT_ENDPOINT=...
AZURE_AI_MODEL_DEPLOYMENT_NAME=...
```

VSCode Python extension automatically loads `.env` files.

Alternatively, pass configuration directly:
```python
from agent_framework.azure import AzureOpenAIChatClient

chat_client = AzureOpenAIChatClient(
    api_key="...",
    endpoint="...",
    deployment_name="...",
    api_version="..."
)
```

## VSCode Setup

### Python

1. Open the `python/` folder as workspace root
2. Install Python extension
3. Run `Python: Select Interpreter` and choose `.venv` virtual environment
4. VSCode will automatically load `.env` files

### .NET

1. Open the `dotnet/` folder or root
2. Install C# extension
3. Solution files auto-detected for IntelliSense

## Additional Resources

- **Microsoft Learn**: https://learn.microsoft.com/agent-framework/
- **GitHub Issues**: https://github.com/microsoft/agent-framework/issues
- **Discord**: https://discord.gg/b5zjErwbQM
- **Design Docs**: `docs/design/`
- **ADRs**: `docs/decisions/`
- **Migration from Semantic Kernel**: https://learn.microsoft.com/agent-framework/migration-guide/from-semantic-kernel
- **Migration from AutoGen**: https://learn.microsoft.com/agent-framework/migration-guide/from-autogen
