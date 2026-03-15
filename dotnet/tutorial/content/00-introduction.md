# Introduction to the Microsoft Agent Framework

The **Microsoft Agent Framework (MAF)** is a .NET library for building AI agents — autonomous programs that reason, remember, and act using large language models.

MAF provides a clean, composable API on top of `Microsoft.Extensions.AI`, making it easy to:

- Create agents backed by any LLM provider (Azure OpenAI, OpenAI, and more)
- Give agents tools (local functions, external APIs)
- Maintain multi-turn conversations with session state
- Build complex multi-agent workflows
- Host agents as production services

## Why MAF?

| Without MAF | With MAF |
|---|---|
| Manage raw HTTP calls to LLM APIs | `agent.RunAsync("...")` |
| Manually track conversation history | `AgentSession` handles it |
| Wire up function calling protocol | Decorate methods with `[Description]` |
| Build custom orchestration | `WorkflowBuilder` + edges |

## Getting Started

### Prerequisites

- .NET 10 SDK
- An Azure OpenAI resource (or OpenAI API key)
- Two environment variables:

```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
```

### Your First Agent (5 lines)

```csharp
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Chat;

AIAgent agent = new AzureOpenAIClient(
    new Uri(Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")!),
    new DefaultAzureCredential())
    .GetChatClient("gpt-4o-mini")
    .AsAIAgent(instructions: "You are a helpful assistant.");

Console.WriteLine(await agent.RunAsync("Hello!"));
```

The key extension method is `.AsAIAgent()` — it wraps any `IChatClient` into a full `AIAgent`.

## Tutorial Structure

This tutorial walks through the six official get-started samples:

1. **Hello Agent** — create and invoke a basic agent
2. **Adding Tools** — give the agent local functions to call
3. **Multi-Turn Conversations** — preserve context across messages
4. **Agent Memory** — custom `AIContextProvider` for persistent state
5. **Your First Workflow** — executors and edges
6. **Hosting Your Agent** — Azure Functions with DurableAgents

Each chapter shows the complete, runnable `Program.cs` from the corresponding sample, then explains what each part does.

## Source Code

All samples live under `dotnet/samples/01-get-started/` in this repository.
