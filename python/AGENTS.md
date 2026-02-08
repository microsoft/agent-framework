# AGENTS.md

Instructions for AI coding agents working in the Python codebase.

**Key Documentation:**
- [DEV_SETUP.md](DEV_SETUP.md) - Development environment setup and available poe tasks
- [CODING_STANDARD.md](CODING_STANDARD.md) - Coding standards, docstring format, and performance guidelines

## Maintaining Documentation

When making changes to a package, check if the package's `AGENTS.md` file needs updates. This includes:
- Adding/removing/renaming public classes or functions
- Changing the package's purpose or architecture
- Modifying import paths or usage patterns

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
└── tests/                    # Integration tests
```

### Package Relationships

- `agent-framework-core` contains core abstractions and OpenAI/Azure OpenAI built-in
- Provider packages (`azure-ai`, `anthropic`, etc.) extend core with specific integrations
- Core uses lazy loading via `__getattr__` in provider folders (e.g., `agent_framework/azure/`)

### Import Patterns

```python
# Core imports
from agent_framework import ChatAgent, ChatMessage, tool

# Provider imports (lazy-loaded)
from agent_framework.openai import OpenAIChatClient
from agent_framework.azure import AzureOpenAIChatClient, AzureAIAgentClient
```

## Key Conventions

- **Copyright**: `# Copyright (c) Microsoft. All rights reserved.` at top of all `.py` files
- **Types**: Always specify return types and parameter types; use `Type | None` not `Optional`
- **Logging**: `from agent_framework import get_logger` (never `import logging`)
- **Docstrings**: Google-style for public APIs
- **Tests**: Do not use `@pytest.mark.asyncio` (auto mode enabled); run only related tests, not the entire suite
- **Line length**: 120 characters
- **Comments**: Avoid excessive comments; prefer clear code
- **Formatting**: Format only files you changed, not the entire codebase

## Sample Structure

1. Copyright header: `# Copyright (c) Microsoft. All rights reserved.`
2. Required imports
3. Module docstring: `"""This sample demonstrates..."""`
4. Helper functions
5. Main function(s) demonstrating functionality
6. Entry point: `if __name__ == "__main__": asyncio.run(main())`

When modifying samples, update associated README files in the same or parent folders.

### Samples Syntax Checking

Run `uv run poe samples-syntax` to check samples for syntax errors and missing imports from `agent_framework`. This uses a relaxed pyright configuration that validates imports without strict type checking.

Some samples depend on external packages (e.g., `azure.ai.agentserver.agentframework`, `microsoft_agents`) that are not installed in the dev environment. These are excluded in `pyrightconfig.samples.json`. When adding or modifying these excluded samples, add them to the exclude list and manually verify they have no import errors from `agent_framework` packages by temporarily removing them from the exclude list and running the check.

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
