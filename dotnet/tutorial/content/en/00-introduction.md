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
- An OpenAI API key (or Anthropic API key — see below)
- Two environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
```

### Creating a New .NET App

Start by creating a new console app and adding the required NuGet packages:

```bash
dotnet new console -n MyAgent
cd MyAgent
```

#### NuGet Packages for OpenAI

```bash
dotnet add package Microsoft.Agents.AI --prerelease
dotnet add package Microsoft.Agents.AI.OpenAI --prerelease
dotnet add package Microsoft.Extensions.AI.OpenAI
dotnet add package Azure.AI.OpenAI --prerelease
```

#### NuGet Packages for Anthropic (Claude)

If you want to use Claude instead of OpenAI, install the Anthropic adapter:

```bash
dotnet add package Microsoft.Agents.AI --prerelease
dotnet add package Microsoft.Agents.AI.Anthropic --prerelease
dotnet add package Anthropic
```

#### What Each Package Does

| Package | Purpose |
|---|---|
| `Microsoft.Agents.AI` | Core MAF library — `AIAgent`, `AgentSession`, `WorkflowBuilder`, tool support |
| `Microsoft.Agents.AI.OpenAI` | MAF adapter for OpenAI — adds `.AsAIAgent()` to `IChatClient` |
| `Microsoft.Extensions.AI.OpenAI` | Microsoft's official OpenAI bridge for `Microsoft.Extensions.AI` |
| `Azure.AI.OpenAI` | Azure OpenAI SDK (also used for standard openai.com endpoints) |
| `Microsoft.Agents.AI.Anthropic` | MAF first-party adapter for Anthropic — adds `.AsAIAgent()` directly to `AnthropicClient` |
| `Anthropic` | Official Anthropic .NET SDK (`AnthropicClient`, model streaming, etc.) |

> **Why both `Microsoft.Agents.AI.Anthropic` and `Anthropic`?**
> The `Anthropic` package is Anthropic's own SDK and handles the raw HTTP transport.
> `Microsoft.Agents.AI.Anthropic` wraps it into MAF's `AIAgent` abstraction so you get sessions, tools, memory, and workflows — the same as with OpenAI.

### Your First Agent (5 lines)

```csharp
using Microsoft.Agents.AI;
using OpenAI;
using OpenAI.Chat;

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
