# CLAUDE.md - Agent Framework AI Assistant Guide

> **Last Updated**: 2026-01-01
> **Purpose**: Guide for AI assistants working on this codebase

---

## Architecture

### Overview
Multi-language AI Agent Framework (Python + .NET) for building LLM-powered agents with workflow orchestration.

### Directory Structure
```
/
├── python/                    # Python implementation (3.10+)
│   ├── packages/
│   │   ├── core/              # Core abstractions (agents, tools, middleware, workflows)
│   │   ├── openai/            # OpenAI provider
│   │   ├── azure-ai/          # Azure AI Foundry integration
│   │   ├── a2a/               # Agent-to-Agent communication
│   │   ├── copilotstudio/     # Copilot Studio integration
│   │   ├── devui/             # Interactive developer UI (React + FastAPI)
│   │   ├── lab/               # Experimental modules (GAIA, Lightning, Tau2)
│   │   ├── mem0/              # Mem0 memory integration
│   │   └── redis/             # Redis context provider
│   ├── samples/getting_started/
│   └── tests/
│
├── dotnet/                    # .NET implementation (NET 9.0)
│   ├── src/
│   │   ├── Microsoft.Agents.AI/
│   │   ├── Microsoft.Agents.AI.Abstractions/
│   │   ├── Microsoft.Agents.AI.OpenAI/
│   │   ├── Microsoft.Agents.AI.AzureAI/
│   │   ├── Microsoft.Agents.AI.Workflows/
│   │   ├── Microsoft.Agents.AI.Workflows.Declarative/
│   │   ├── Microsoft.Agents.AI.A2A/
│   │   └── Microsoft.Agents.AI.Hosting*/
│   ├── samples/               # 80+ sample projects
│   └── tests/                 # 18 test projects
│
├── docs/
│   ├── decisions/             # ADRs (Architectural Decision Records)
│   ├── design/                # Design documents
│   └── specs/                 # Technical specifications
│
└── workflow-samples/          # Cross-language workflow examples
```

### Design Patterns
- **Layered Architecture**: Abstractions → Core → Provider-specific implementations
- **Graph-Based Workflows**: DAG structure with executors/edges, streaming, checkpoints
- **Provider Pattern**: Multiple LLM providers (OpenAI, Azure OpenAI, Ollama, ONNX)
- **Middleware Pipeline**: Request/response interception, async-first design
- **Plugin/Tool System**: Declarative function definitions with approval workflow
- **Context/Memory Pattern**: Thread management, Redis/Mem0 storage integration
- **Declarative Workflows**: JSON/YAML definitions with PowerFx expressions

### Key ADRs (docs/decisions/)
| ADR | Topic |
|-----|-------|
| 0001 | Agent Run Response Pattern |
| 0002 | Agent Tools/Functions |
| 0003 | OpenTelemetry Instrumentation |
| 0006 | User Approval Workflows |
| 0007 | Filtering Middleware |

---

## Commands

### Python Development

```bash
# Setup (one-command)
uv run poe setup -p 3.13

# Or manual setup
uv python install 3.10 3.11 3.12 3.13
uv venv --python 3.10
uv sync --dev
uv run poe install

# Development
uv run poe fmt          # Format code (ruff)
uv run poe lint         # Lint code (ruff)
uv run poe pyright      # Type check (pyright)
uv run poe mypy         # Type check (mypy)

# Testing
uv run poe all-tests              # Run all tests
uv run poe all-tests-cov          # Tests with coverage
uv run poe check                  # Full check suite (fmt, lint, type, test)

# Build
uv run poe build                  # Build all packages
uv run poe docs-build             # Generate documentation
```

### .NET Development

```bash
# Build
dotnet build

# Test
dotnet test

# Format
dotnet format
```

### Quick Reference
| Task | Python | .NET |
|------|--------|------|
| Install | `uv sync --dev` | `dotnet restore` |
| Dev/Format | `uv run poe fmt` | `dotnet format` |
| Lint | `uv run poe lint` | `dotnet format --verify-no-changes` |
| Test | `uv run poe all-tests` | `dotnet test` |
| Build | `uv run poe build` | `dotnet build` |

---

## Conventions

### Python
- **Version**: Python >= 3.10
- **Package Manager**: `uv` (workspace-based monorepo)
- **Linter/Formatter**: `ruff` (line-length: 120, preview mode)
- **Type Checking**: `pyright` + `mypy` (strict mode)
- **Security**: `bandit` for vulnerability scanning
- **Testing**: `pytest` with `pytest-asyncio`, `pytest-cov`, `pytest-xdist`
- **Pre-commit**: Enforced hooks for TOML/YAML/JSON, ruff, bandit

### .NET
- **Version**: .NET 9.0 (SDK 9.0.300)
- **Style**: `.editorconfig` enforced
- **Package Management**: Central Package Management enabled
- **Testing**: xUnit framework

### TypeScript (DevUI)
- **Framework**: React 19 + TypeScript 5.8
- **Build Tool**: Vite 7.1
- **Linter**: ESLint 9.33 with TypeScript support
- **Styling**: Tailwind CSS 4.1

### Code Quality Rules
1. **Strict typing** required in Python (pyright/mypy strict mode)
2. **Docstrings** for public APIs (ruff D rules)
3. **Async-first** design for I/O operations
4. **No TODO without assignee** (enforced by ruff TD)
5. **Security scanning** via bandit and CodeQL

### Preferred Libraries
| Purpose | Python | .NET |
|---------|--------|------|
| HTTP | `httpx`, `aiohttp` | `HttpClient` |
| Validation | `pydantic` | `DataAnnotations` |
| Async | `asyncio`, `anyio` | `async/await` |
| AI/LLM | `openai>=1.99` | `Microsoft.Extensions.AI` |
| Observability | `opentelemetry-*` | `OpenTelemetry.*` |
| Azure Auth | `azure-identity` | `Azure.Identity` |

### Version Info
- **Python Package**: `1.0.0b251001` (beta)
- **NuGet Package**: `1.0.0-preview.251001.3`

---

## CI/CD Workflows (.github/workflows/)
| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `python-tests.yml` | Python changes | Multi-version tests (3.10-3.13) |
| `python-code-quality.yml` | Python changes | Linting, type checking |
| `dotnet-build-and-test.yml` | .NET changes | Build + test (net9.0, net472) |
| `codeql-analysis.yml` | All changes | Security analysis |

---

## Known TODOs (101 total)
Priority items requiring attention:
- Content type support expansion (`_tools.py`, `_responses_client.py`)
- Executor factories for lazy initialization (`_workflow.py`)
- macOS test re-enablement (`python-lab-tests.yml`)
- Sample folder structure reorganization

---

## Quick Start for New Contributors
1. Clone repo and run `uv run poe setup -p 3.13` (Python) or `dotnet build` (.NET)
2. Read ADRs in `docs/decisions/` for architectural context
3. Check `samples/` directories for usage examples
4. Run `uv run poe check` or `dotnet test` before committing
