# Development Processes

## Purpose
This document describes the standard development workflows and processes for contributing to the Microsoft Agent Framework.

## Classification
- **Domain:** Process
- **Stability:** Semi-stable
- **Abstraction:** Procedural
- **Confidence:** Established

## Development Setup

### Python Development

#### Prerequisites
Install `uv` package manager:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS (Homebrew)
brew install uv

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### Initial Setup

From the `python/` directory:

```bash
# Quick setup with Python 3.13
uv run poe setup -p 3.13

# Manual setup
uv python install 3.10 3.11 3.12 3.13
uv venv --python 3.13
uv sync --dev
uv run poe install
uv run poe pre-commit-install
```

#### Common Development Commands

```bash
# Format code (ruff)
uv run poe fmt

# Run linting
uv run poe lint

# Run type checking
uv run poe pyright
uv run poe mypy

# Run tests with coverage
uv run poe test

# Run all quality checks (format, lint, type check, test)
uv run poe check

# Run pre-commit checks (excludes mypy)
uv run poe pre-commit-check
```

#### Running Tests

```bash
# All tests with coverage
uv run poe test

# Single package tests (from python/ directory)
uv run poe --directory packages/core test

# Single test file
uv run pytest tests/test_agents.py

# Verbose output
uv run pytest -v

# Integration tests (requires environment variables)
RUN_INTEGRATION_TESTS=true uv run pytest
```

#### Building Documentation

```bash
# Build documentation
uv run poe docs-build

# Serve locally with auto-reload
uv run poe docs-serve

# Full rebuild (clean + build)
uv run poe docs-rebuild
```

### .NET Development

From the `dotnet/` directory:

```bash
# Build
dotnet build

# Run tests
dotnet test

# Auto-fix linting issues
dotnet format
```

## Environment Configuration

### Python API Keys

Create `.env` file in `python/` directory:

```env
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

Alternatively, pass configuration directly in code:
```python
from agent_framework.azure import AzureOpenAIChatClient

chat_client = AzureOpenAIChatClient(
    api_key="...",
    endpoint="...",
    deployment_name="...",
    api_version="..."
)
```

## Contribution Workflow

### 1. Before Starting Work

1. **File an issue** for non-trivial changes
   - Skip for trivial changes (typos, small fixes)
   - Reuse existing issues when applicable
2. **Get agreement** from team and community
3. **Clearly state** you're taking on the work
4. **Request assignment** to the issue

### 2. Create Branch

```bash
# Create a personal fork if you haven't already
# Clone your fork locally

# Create branch off main
git checkout -b issue-123
# or
git checkout -b feature-name
```

Branch naming conventions:
- `issue-123` - For bug fixes
- `feature-name` - For new features
- `githubhandle-description` - Personal branches

### 3. Development Cycle

1. **Make changes** in your branch
2. **Write tests** for new features or bug fixes
3. **Run quality checks**:
   - Python: `uv run poe check`
   - .NET: `dotnet build && dotnet test && dotnet format`
4. **Commit changes** with clear messages
5. **Keep commits focused** on single logical changes

### 4. Testing Requirements

- **New features**: Must include tests
- **Bug fixes**: Start with a failing test that demonstrates the bug
- **Coverage**: Maintain or improve test coverage
- **Integration tests**: Mark appropriately and test with required environment variables

### 5. Create Pull Request

1. **Push branch** to your fork
2. **Create PR** against `main` branch of `microsoft/agent-framework`
3. **PR Description**:
   - State what issue or improvement is being addressed
   - Provide context on the changes
   - Include testing notes
   - Reference related issues

### 6. PR Review Process

1. **Verify CI checks** pass (all green)
2. **Respond to feedback** from maintainers
3. **Make requested changes** in your branch
4. **Wait for approval** from code owners
5. **Merge** occurs after approval and passing checks

## Code Quality Standards

### Python

Refer to [Development Principles](../foundation/principles.md#python-standards) for complete standards.

Key points:
- Use `ruff` for formatting (line length: 120)
- Google-style docstrings required
- Type hints with `pyright` strict mode
- Async-first design
- Centralized logging via `get_logger()`

### .NET

Refer to [Development Principles](../foundation/principles.md#net-standards) for complete standards.

Key points:
- Follow [.NET coding conventions](https://learn.microsoft.com/dotnet/csharp/fundamentals/coding-style/coding-conventions)
- Use `dotnet format` for consistency
- XML documentation comments for public APIs
- Async/await for I/O operations

## Context Network Guidelines

When working on the repository:

1. **Consult context network** before implementing features
2. **Document decisions** in appropriate sections:
   - Major decisions → `decisions/` (ADRs)
   - Design documentation → `design/`
   - Specifications → `specs/`
3. **Update relationship maps** when creating dependencies
4. **Planning documents go in context network**, not project root

## VSCode Setup

### Python

1. Open `python/` folder as workspace root
2. Install Python extension
3. Run `Python: Select Interpreter` → Choose `.venv`
4. VSCode will automatically load `.env` files

### .NET

1. Open `dotnet/` folder or repository root
2. Install C# extension
3. Solution files auto-detected for IntelliSense

## Pre-commit Hooks

Python projects use pre-commit hooks for quality checks:

```bash
# Install hooks (done automatically with setup)
uv run poe pre-commit-install

# Run manually
uv run pre-commit run -a
```

Hooks run automatically on `git commit` and check:
- Code formatting (ruff)
- Linting (ruff)
- Type checking (pyright)
- Test execution (pytest)

## Troubleshooting

### Python Issues

**Import errors after adding dependencies:**
```bash
uv sync --dev
uv run poe install
```

**Pre-commit hooks failing:**
```bash
uv run poe pre-commit-check
# Fix any issues reported
```

**Type checking errors:**
```bash
uv run poe pyright
# Address type errors
```

### .NET Issues

**Build errors:**
```bash
dotnet clean
dotnet restore
dotnet build
```

**Test failures:**
```bash
dotnet test --logger "console;verbosity=detailed"
```

## Relationship Network
- **Prerequisite Information**:
  - [Project Definition](../foundation/project_definition.md)
  - [Development Principles](../foundation/principles.md)
- **Related Information**:
  - [Testing Procedures](testing.md)
  - [Contributing Guide](contributing.md)
- **Implementation Details**:
  - Python setup: `python/DEV_SETUP.md`
  - .NET setup: `dotnet/README.md`

## Navigation Guidance
- **Access Context**: When starting development work or troubleshooting setup
- **Common Next Steps**:
  - Understanding principles → [Development Principles](../foundation/principles.md)
  - Testing → [Testing Procedures](testing.md)
  - Contributing → [Contributing Guide](contributing.md)
- **Related Tasks**: Feature development, bug fixes, testing, code reviews

## Metadata
- **Created:** 2025-10-11
- **Last Updated:** 2025-10-11
- **Updated By:** Context Network Setup

## Change History
- 2025-10-11: Initial document created during context network setup based on python/DEV_SETUP.md and CLAUDE.md
