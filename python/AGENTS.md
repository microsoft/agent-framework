# AGENTS.md

Instructions for AI coding agents working in the Python codebase.

**Key Documentation:**
- [DEV_SETUP.md](DEV_SETUP.md) - Development environment setup and available poe tasks
- [CODING_STANDARD.md](CODING_STANDARD.md) - Coding standards, docstring format, and performance guidelines
- [samples/SAMPLE_GUIDELINES.md](samples/SAMPLE_GUIDELINES.md) - Sample structure and guidelines

**Agent Skills** (`.github/skills/`) — detailed, task-specific instructions loaded on demand:
- `python-development` — coding standards, type annotations, docstrings, logging, performance
- `python-testing` — test structure, fixtures, async mode, running tests
- `python-code-quality` — linting, formatting, type checking, prek hooks, CI workflow
- `python-package-management` — monorepo structure, lazy loading, versioning, new packages
- `python-samples` — sample file structure, PEP 723, documentation guidelines

## Maintaining Documentation

When making changes to a package, check if the following need updates:
- The package's `AGENTS.md` file (adding/removing/renaming public APIs, architecture changes, import path changes)
- The agent skills in `.github/skills/` if conventions, commands, or workflows change

## Quick Reference

Run `uv run poe` from the `python/` directory to see available commands. See [DEV_SETUP.md](DEV_SETUP.md) for detailed usage.

## Project Structure

```
python/
├── packages/
│   ├── core/                 # agent-framework-core (main package)
│   │   ├── agent_framework/  # Public API exports
│   │   └── tests/
│   ├── azure-ai/             # agent-framework-azure-ai
│   ├── anthropic/            # agent-framework-anthropic
│   ├── ollama/               # agent-framework-ollama
│   └── ...                   # Other provider packages
├── samples/                  # Sample code and examples
├── .github/skills/           # Agent skills for Copilot
└── tests/                    # Integration tests
```

### Package Relationships

- `agent-framework-core` contains core abstractions and OpenAI/Azure OpenAI built-in
- Provider packages (`azure-ai`, `anthropic`, etc.) extend core with specific integrations
- Core uses lazy loading via `__getattr__` in provider folders (e.g., `agent_framework/azure/`)

## Package Documentation

### Core
- [core](packages/core/AGENTS.md) - Core abstractions, types, and built-in OpenAI/Azure OpenAI support

### LLM Providers
- [anthropic](packages/anthropic/AGENTS.md) - Anthropic Claude API
- [bedrock](packages/bedrock/AGENTS.md) - AWS Bedrock
- [claude](packages/claude/AGENTS.md) - Claude Agent SDK
- [foundry_local](packages/foundry_local/AGENTS.md) - Azure AI Foundry Local
- [ollama](packages/ollama/AGENTS.md) - Local Ollama inference

### Azure Integrations
- [azure-ai](packages/azure-ai/AGENTS.md) - Azure AI Foundry agents
- [azure-ai-search](packages/azure-ai-search/AGENTS.md) - Azure AI Search RAG
- [azurefunctions](packages/azurefunctions/AGENTS.md) - Azure Functions hosting

### Protocols & UI
- [a2a](packages/a2a/AGENTS.md) - Agent-to-Agent protocol
- [ag-ui](packages/ag-ui/AGENTS.md) - AG-UI protocol
- [chatkit](packages/chatkit/AGENTS.md) - OpenAI ChatKit integration
- [devui](packages/devui/AGENTS.md) - Developer UI for testing

### Storage & Memory
- [mem0](packages/mem0/AGENTS.md) - Mem0 memory integration
- [redis](packages/redis/AGENTS.md) - Redis storage

### Infrastructure
- [copilotstudio](packages/copilotstudio/AGENTS.md) - Microsoft Copilot Studio
- [declarative](packages/declarative/AGENTS.md) - YAML/JSON agent definitions
- [durabletask](packages/durabletask/AGENTS.md) - Durable execution
- [github_copilot](packages/github_copilot/AGENTS.md) - GitHub Copilot extensions
- [purview](packages/purview/AGENTS.md) - Data governance

### Experimental
- [lab](packages/lab/AGENTS.md) - Experimental features
