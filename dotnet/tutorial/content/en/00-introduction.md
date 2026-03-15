# Introduction to the Microsoft Agent Framework

The **Microsoft Agent Framework (MAF)** is a .NET library for building AI agents — autonomous programs that reason, remember, and act using large language models.

MAF provides a clean, composable API on top of `Microsoft.Extensions.AI`, making it easy to:

- Create agents backed by any LLM provider (OpenAI, Anthropic, Azure OpenAI, and more)
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
- An OpenAI API key
- Two environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
```

### Your First Agent (5 lines)

```csharp
using Microsoft.Agents.AI;
using OpenAI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(instructions: "You are a helpful assistant.");

Console.WriteLine(await agent.RunAsync("Hello!"));
```

The key extension method is `.AsAIAgent()` — it wraps any `IChatClient` into a full `AIAgent`.

### Alternative: Anthropic (Claude)

MAF has a first-party Anthropic adapter via the `Microsoft.Agents.AI.Anthropic` package. The pattern is slightly different — `AnthropicClient` exposes `.AsAIAgent()` directly:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL="claude-haiku-4-5"
```

```csharp
using Anthropic;
using Microsoft.Agents.AI;

var apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY")
    ?? throw new InvalidOperationException("ANTHROPIC_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("ANTHROPIC_MODEL") ?? "claude-haiku-4-5";

using AnthropicClient client = new AnthropicClient() { ApiKey = apiKey };

AIAgent agent = client.AsAIAgent(
    model: model,
    instructions: "You are a helpful assistant.");

Console.WriteLine(await agent.RunAsync("Hello!"));
```

The rest of the tutorial uses OpenAI, but every pattern — sessions, tools, memory, workflows — works identically with Anthropic.

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
