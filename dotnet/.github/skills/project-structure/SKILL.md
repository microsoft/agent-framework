---
name: project-structure
description: Explains the project structure of the agent-framework .NET solution
---

# Agent Framework .NET Project Structure

```
dotnet/
├── src/
│   ├── Microsoft.Agents.AI/                      # Core AI agent implementations
│   ├── Microsoft.Agents.AI.Abstractions/         # Core AI agent abstractions
│   ├── Microsoft.Agents.AI.A2A/                  # Agent-to-Agent (A2A) provider
│   ├── Microsoft.Agents.AI.OpenAI/               # OpenAI provider
│   ├── Microsoft.Agents.AI.AzureAI/              # Azure AI Foundry Agents (v2) provider
│   ├── Microsoft.Agents.AI.AzureAI.Persistent/   # Legacy Azure AI Foundry Agents (v1) provider
│   ├── Microsoft.Agents.AI.Anthropic/            # Anthropic provider
│   ├── Microsoft.Agents.AI.Workflows/            # Workflow orchestration
│   └── ...                                       # Other packages
├── samples/                                      # Sample applications
└── tests/                                        # Unit and integration tests
```

## Main Folders

| Folder | Contents |
|--------|----------|
| `src/` | Source code projects |
| `tests/` | Test projects — named `<Source-Code-Project>.UnitTests` or `<Source-Code-Project>.IntegrationTests` |
| `samples/` | Sample projects |
| `src/Shared`, `src/LegacySupport` | Shared code files included by multiple source code projects (see README.md files in these folders or their subdirectories for instructions on how to include them in a project) |
