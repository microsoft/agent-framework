# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

Microsoft Agent Framework is a comprehensive multi-language framework for building, orchestrating, and deploying AI agents. This private preview project supports both .NET and Python implementations, providing everything from simple chat agents to complex multi-agent workflows with graph-based orchestration.

**Key Features:**
- Multi-Agent Orchestration: group chat, sequential, concurrent, and handoff patterns
- Graph-based Workflows: data flows with streaming, checkpointing, time-travel, and Human-in-the-loop
- Plugin Ecosystem: native functions, OpenAPI, Model Context Protocol (MCP)
- LLM Support: OpenAI, Azure OpenAI, Azure AI Foundry
- Runtime Support: in-process and distributed agent execution
- Cross-Platform: .NET and Python implementations with shared architecture

## Repository Structure

The repository is organized as a multi-language monorepo:

```
agent-framework/
├── python/                  # Python implementation
│   ├── packages/           # Core packages
│   │   ├── main/          # Core agent framework
│   │   ├── azure/         # Azure integration
│   │   ├── foundry/       # Azure AI Foundry integration
│   │   ├── copilotstudio/ # Copilot Studio integration
│   │   ├── mem0/          # Memory integration
│   │   ├── runtime/       # Distributed runtime
│   │   └── workflow/      # Workflow orchestration
│   └── samples/           # Python examples and tutorials
├── dotnet/                 # .NET implementation
│   ├── src/              # Core .NET packages
│   ├── samples/          # .NET examples and tutorials
│   ├── demos/            # Demo applications
│   └── tests/            # .NET test suites
├── workflows/              # Declarative YAML workflow examples
├── docs/                   # Design documents and ADRs
└── user-documentation-*/   # User guides for both languages
```

## Core Architecture Concepts

### Agent Types
- **ChatAgent**: Basic conversational agent with tool support
- **Multi-Agent Orchestration**: Sequential, concurrent, and group chat patterns
- **Workflow Agents**: Graph-based orchestration with deterministic functions

### Integration Layers
- **Chat Clients**: Abstraction over different LLM providers (OpenAI, Azure OpenAI, Foundry)
- **Tool System**: Function calling, OpenAPI integration, MCP connectors
- **Context Providers**: Vector stores, memory systems, guardrails
- **Runtime**: Local and distributed execution environments

### Workflow System
Declarative workflows defined in YAML can be executed both locally and hosted in Azure Foundry Projects. Workflows connect agents and deterministic functions using data flows.

## Common Development Commands

### Python Development

**Setup and Installation:**
```bash
# Install uv (dependency manager)
# Windows (PowerShell):
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# Linux/macOS:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup development environment
cd python
uv run poe setup --python 3.13
```

**Core Development Tasks:**
```bash
# Install dependencies and setup
uv run poe install

# Code formatting and linting
uv run poe fmt          # Format code with ruff
uv run poe lint         # Run linting checks

# Type checking
uv run poe pyright      # Run Pyright type checker
uv run poe mypy         # Run MyPy type checker

# Testing
uv run poe test         # Run all tests with coverage
uv run poe all-tests    # Run comprehensive test suite

# Run all quality checks
uv run poe check        # Runs fmt, lint, pyright, mypy, test, and markdown checks
```

**Running Samples:**
```bash
# Run Python samples directly (no package installation needed)
cd python/samples/getting_started
python minimal_sample.py

# Run specific package tests
uv run poe --directory packages/main test
```

### .NET Development

**Setup:**
```powershell
# Requires .NET 8.0+ (SDK 9.0.300+ recommended)
cd dotnet/demos/MinimalConsole
dotnet build
```

**Core Development Tasks:**
```powershell
# Build projects
dotnet build

# Run demos/samples
dotnet run --framework net9.0 --no-build

# Run tests
dotnet test

# Run specific sample
cd dotnet/samples/GettingStarted/Agents/Agent_Step01_Running
dotnet run
```

### Cross-Platform Commands

**Documentation:**
```bash
# Python docs
cd python
uv run poe docs-build       # Build documentation
uv run poe docs-full        # Build packages and docs
uv run poe docs-rebuild     # Clean and rebuild docs

# Check markdown code blocks
uv run poe markdown-code-lint
```

**Pre-commit Hooks:**
```bash
cd python
uv run poe pre-commit-install  # Install hooks
uv run pre-commit run -a       # Run all hooks manually
```

## Environment Configuration

### Required Environment Variables

**For OpenAI:**
```bash
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL_ID=gpt-4o-mini
```

**For Azure OpenAI:**
```bash
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://<deployment>.openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=...
```

**For Azure Foundry:**
```bash
FOUNDRY_PROJECT_ENDPOINT=...
FOUNDRY_MODEL_DEPLOYMENT_NAME=...
```

### Development Environment Setup

Create a `.env` file in the project root or use separate environment files:

```bash
# Python: Load from .env or pass env_file_path parameter
from agent_framework.openai import OpenAIChatClient
chat_client = OpenAIChatClient(env_file_path="openai.env")

# .NET: Uses standard environment variable loading
$env:AZURE_OPENAI_ENDPOINT = "https://your-deployment.openai.azure.com/"
```

## Package Installation Notes

**Important:** Public PyPI and NuGet packages are not yet available during private preview.

**Option 1:** Run samples directly from repository (recommended for development)
**Option 2:** Install nightly packages following the guides in `user-documentation-*/getting-started/`

## Testing Strategy

- **Unit Tests**: Located in `*/tests/` directories
- **Integration Tests**: Require `RUN_INTEGRATION_TESTS=true` environment variable and appropriate API keys
- **Coverage Target**: Minimum 80% for all packages
- **Test Markers**: `@azure`, `@foundry`, `@openai` for provider-specific tests

## Code Quality Standards

### Python
- **Line Length**: 120 characters
- **Target Version**: Python 3.10+
- **Docstring Style**: Google conventions
- **Type Checking**: Strict mode with Pyright and MyPy
- **Linting**: Ruff with extensive rule set including security checks (Bandit)

### .NET
- **Framework**: .NET 8.0+, targeting net9.0, net8.0, netstandard2.0, net472
- **Standard**: Follow Microsoft C# coding conventions

## Development Workflow Tips

1. **Package Development**: Use workspace setup with `uv` for Python to work with local packages as if installed
2. **Workflow Testing**: Use declarative workflows in `/workflows/` directory with the .NET demo
3. **Multi-Agent Patterns**: Reference orchestration samples in `dotnet/samples/GettingStarted/Orchestration/`
4. **Integration Testing**: Set up appropriate cloud resources and environment variables for provider testing
5. **Documentation**: Both implementations share conceptual documentation in `/docs/` with language-specific guides in user documentation directories

## Architecture Decision Records

Refer to `/docs/decisions/` for detailed architectural decisions and design documents in `/docs/design/` for understanding the framework's design principles.