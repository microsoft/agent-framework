# Samples Structure & Design Choices — .NET

> This file documents the structure and conventions of the .NET samples so that
> agents (AI or human) can maintain them without rediscovering decisions.

## Directory layout

```
dotnet/samples/
├── 01-get-started/                    # Progressive tutorial (steps 01–06)
│   ├── 01_hello_agent/                # Create and run your first agent
│   ├── 02_add_tools/                  # Add function tools
│   ├── 03_multi_turn/                 # Multi-turn conversations with AgentSession
│   ├── 04_memory/                     # Agent memory with AIContextProvider
│   ├── 05_first_workflow/             # Build a workflow with executors and edges
│   └── 06_host_your_agent/            # Host your agent via Azure Functions
├── 02-agents/                         # Deep-dive concept samples
│   ├── Agents/                        # Core agent patterns (tools, structured output,
│   │                                  #   conversations, middleware, plugins, MCP, etc.)
│   ├── AgentProviders/                # Provider-grouped samples
│   │   ├── a2a/                       # A2A provider sample
│   │   ├── anthropic/                 # Anthropic provider samples
│   │   ├── azure/                     # Azure/OpenAI/Foundry model provider samples
│   │   ├── custom/                    # Custom agent implementation sample
│   │   ├── foundry/                   # Microsoft Foundry agent samples
│   │   ├── github-copilot/            # GitHub Copilot provider sample
│   │   ├── google-gemini/             # Google Gemini provider sample
│   │   ├── ollama/                    # Ollama provider sample
│   │   ├── onnx/                      # ONNX Runtime provider sample
│   │   └── openai/                    # OpenAI provider samples
│   ├── AgentOpenTelemetry/            # OpenTelemetry integration
│   ├── AgentSkills/                   # Agent skills patterns
│   ├── AgentWithMemory/               # Memory providers (chat history, Mem0, Foundry)
│   ├── AgentWithRAG/                  # RAG patterns (text, vector store, Foundry)
│   ├── AGUI/                          # AG-UI protocol samples
│   ├── DeclarativeAgents/             # Declarative agent definitions
│   ├── DevUI/                         # DevUI samples
│   └── ModelContextProtocol/          # MCP server/client patterns
├── 03-workflows/                      # Workflow patterns
│   ├── _StartHere/                    # Introductory workflow samples
│   ├── Agents/                        # Agents in workflows
│   ├── Checkpoint/                    # Checkpointing & resume
│   ├── Concurrent/                    # Concurrent execution
│   ├── ConditionalEdges/              # Conditional routing
│   ├── Declarative/                   # YAML-based workflows
│   ├── HumanInTheLoop/                # HITL patterns
│   ├── Loop/                          # Loop patterns
│   ├── Observability/                 # Workflow telemetry
│   ├── SharedStates/                  # State isolation
│   └── Visualization/                 # Workflow visualization
├── 04-hosting/                        # Deployment & hosting
│   ├── A2A/                           # Agent-to-Agent protocol
│   └── DurableAgents/                 # Durable task framework
│       ├── AzureFunctions/            #   Azure Functions hosting
│       └── ConsoleApps/               #   Console app hosting
├── 05-end-to-end/                     # Complete applications
│   ├── A2AClientServer/               # A2A client/server demo
│   ├── AgentWebChat/                  # Aspire-based web chat
│   ├── AgentWithPurview/              # Purview integration
│   ├── AGUIClientServer/              # AG-UI client/server demo
│   ├── AGUIWebChat/                   # AG-UI web chat
│   ├── HostedAgents/                  # Hosted agent scenarios
│   └── M365Agent/                     # Microsoft 365 agent
```

## Design principles

1. **Progressive complexity**: Sections 01→05 build from "hello world" to
   production. Within 01-get-started, projects are numbered 01–06 and each step
   adds exactly one concept.

2. **One concept per project** in 01-get-started. Each step is a standalone
   C# project with a single `Program.cs` file.

3. **Workflows preserved**: 03-workflows/ keeps the upstream folder names
   intact. Do not rename or restructure workflow samples.

4. **Per-project structure**: Each sample is a separate .csproj. Shared build
   configuration is inherited from `Directory.Build.props`.

## Default provider

All canonical samples (01-get-started) use **Microsoft Foundry** via `AIProjectClient.AsAIAgent()` with `DefaultAzureCredential`:

```csharp
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(model: model, instructions: "...", name: "...");
```

Environment variables:
- `FOUNDRY_PROJECT_ENDPOINT` — Your Foundry project endpoint
- `FOUNDRY_MODEL` — Model name (defaults to `gpt-5.4-mini`)

For authentication, run `az login` before running samples.

**Note:** Use `FoundryAgent` only when demonstrating Foundry-managed (prompt) agents specifically — see `02-agents/AgentsWithFoundry/`. For all other samples, use `AIProjectClient.AsAIAgent()`.

**Note:** For samples demonstrating other providers (Azure OpenAI, OpenAI, Anthropic, etc.), see `02-agents/AgentProviders/`.

## Snippet tags for docs integration

Samples embed named snippet regions for future `:::code` integration:

```csharp
// <snippet_name>
code here
// </snippet_name>
```

## Building and running

All samples use project references to the framework source. To build and run:

```bash
cd dotnet/samples/01-get-started/01_hello_agent
dotnet run
```

## Current API notes

- `AIAgent` is the primary agent abstraction (created via `ChatClient.AsAIAgent(...)`)
- `AgentSession` manages multi-turn conversation state
- `AIContextProvider` injects memory and context
- Prefer `AIProjectClient.AsAIAgent(...)` for Foundry-backed canonical samples
- Azure Functions hosting uses `ConfigureDurableAgents(options => options.AddAIAgent(agent))`
- Workflows use `WorkflowBuilder` with `Executor<TIn, TOut>` and edge connections
