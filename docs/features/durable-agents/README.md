# Durable agents

## Overview

Durable agents extend the standard Microsoft Agent Framework with **durable state management** powered by the Durable Task framework. An ordinary Agent Framework agent runs in-process: its conversation history lives in memory and is lost when the process ends. A durable agent persists conversation history and execution state in external storage so that sessions survive process restarts, failures, and scale-out events.

| Capability | Ordinary agent | Durable agent |
| --- | --- | --- |
| Conversation history | In-memory only | Durably persisted |
| Failure recovery | State lost on crash | Automatically resumed |
| Multi-instance scale-out | Not supported | Any worker can resume a session |
| Multi-agent orchestrations | Manual coordination | Deterministic, checkpointed workflows |
| Human-in-the-loop | Must keep process alive | Can wait days/weeks with zero compute |
| Hosting | Any process | Console app, Azure Functions, or any Durable Task–compatible host |

> [!NOTE]
> For a step-by-step tutorial and deployment guidance, see [Azure Functions (Durable)](https://learn.microsoft.com/agent-framework/integrations/azure-functions) on Microsoft Learn.

## How durable agents work

Durable agents are implemented on top of [Durable Entities](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-entities) (also called "virtual actors"). Each **agent session** maps to one entity instance whose state contains the full conversation history. When you send a message to a durable agent, the following happens:

1. The message is dispatched to the entity identified by an `AgentSessionId` (a composite of the agent name and a unique session key).
2. The entity loads its persisted `DurableAgentState`, which includes the complete conversation history.
3. The entity invokes the underlying `AIAgent` with the full conversation history, collects the response, and appends both the request and the response to the state.
4. The updated state is persisted back to durable storage automatically.

Because the entity framework serializes access to each entity instance, concurrent messages to the same session are processed one at a time, eliminating race conditions.

### Agent session identity

Every durable agent session is identified by an `AgentSessionId`, which has two components:

- **Name** – the registered name of the agent (case-insensitive).
- **Key** – a unique session key (case-sensitive), typically a GUID.

The session ID is mapped to an underlying Durable Task entity ID with a `dafx-` prefix (e.g., `dafx-joker`). This naming convention is consistent across both .NET and Python implementations.

## Architecture

### .NET

The .NET implementation consists of two NuGet packages:

| Package | Purpose |
| --- | --- |
| `Microsoft.Agents.AI.DurableTask` | Core durable agent types: `DurableAIAgent`, `AgentEntity`, `DurableAgentSession`, `AgentSessionId`, `DurableAgentsOptions`, and the state model. |
| `Microsoft.Agents.AI.Hosting.AzureFunctions` | Azure Functions hosting integration: auto-generated HTTP endpoints, MCP tool triggers, entity function triggers, and the `ConfigureDurableAgents` extension method on `FunctionsApplicationBuilder`. |

Key types:

- **`DurableAIAgent`** – A subclass of `AIAgent` used *inside orchestrations*. Obtained via `context.GetAgent("agentName")`, it routes `RunAsync` calls through the orchestration's entity APIs so that each call is checkpointed.
- **`DurableAIAgentProxy`** – A subclass of `AIAgent` used *outside orchestrations* (e.g., from HTTP triggers or console apps). It signals the entity via `DurableTaskClient` and polls for the response.
- **`AgentEntity`** – The `TaskEntity<DurableAgentState>` that hosts the real agent. It loads the registered `AIAgent` by name, wraps it in an `EntityAgentWrapper`, feeds it the full conversation history, and persists the result.
- **`DurableAgentSession`** – An `AgentSession` subclass that carries the `AgentSessionId`.
- **`DurableAgentsOptions`** – Builder for registering agents and configuring TTL.

### Python

The core Python implementation is in the `agent-framework-durabletask` package (`python/packages/durabletask`). Azure Functions hosting (including `AgentFunctionApp`) is in the separate `agent-framework-azurefunctions` package (`python/packages/azurefunctions`).

Key types:

- **`DurableAIAgent`** – A generic proxy (`DurableAIAgent[TaskT]`) implementing `SupportsAgentRun`. Returns a `TaskT` from `run()` — either an `AgentResponse` (client context) or a `DurableAgentTask` (orchestration context, must be `yield`ed).
- **`DurableAIAgentWorker`** – Wraps a `TaskHubGrpcWorker` and registers agents as durable entities via `add_agent()`.
- **`DurableAIAgentClient`** – Wraps a `TaskHubGrpcClient` for external callers. `get_agent()` returns a `DurableAIAgent[AgentResponse]`.
- **`DurableAIAgentOrchestrationContext`** – Wraps an `OrchestrationContext` for use inside orchestrations. `get_agent()` returns a `DurableAIAgent[DurableAgentTask]`.
- **`AgentEntity`** – Platform-agnostic agent execution logic that manages state, invokes the agent, handles streaming, and calls response callbacks.

## Hosting models

### Azure Functions

The recommended production hosting model. A single call to `ConfigureDurableAgents` (C#) or `AgentFunctionApp` (Python) automatically:

- Registers agent entities with the Durable Task worker.
- Generates HTTP endpoints at `/api/agents/{agentName}/run` for each registered agent.
- Supports `thread_id` query parameter / JSON field and the `x-ms-thread-id` response header for session continuity.
- Supports fire-and-forget via the `x-ms-wait-for-response: false` header (returns HTTP 202).
- Optionally exposes agents as MCP tools.

**C# example:**

```csharp
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options => options.AddAIAgent(agent))
    .Build();
app.Run();
```

**Python example:**

```python
app = AgentFunctionApp(agents=[agent])
```

### Console apps / generic hosts

For self-hosted or non-serverless scenarios, register durable agents via `IServiceCollection.ConfigureDurableAgents` (.NET) or `DurableAIAgentWorker` (Python) with explicit Durable Task worker and client configuration.

**C# example:**

```csharp
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureServices(services =>
    {
        services.ConfigureDurableAgents(
            options => options.AddAIAgent(agent),
            workerBuilder: b => b.UseDurableTaskScheduler(connectionString),
            clientBuilder: b => b.UseDurableTaskScheduler(connectionString));
    })
    .Build();
```

**Python example:**

```python
worker = DurableAIAgentWorker(TaskHubGrpcWorker(host_address="localhost:4001"))
worker.add_agent(agent)
worker.start()
```

## Deterministic multi-agent orchestrations

Durable agents can be composed into deterministic, checkpointed workflows using Durable Task orchestrations. The orchestration framework replays orchestrator code on failure, so completed agent calls are not re-executed.

### Patterns

| Pattern | Description |
| --- | --- |
| **Sequential (chaining)** | Call agents one after another, passing outputs forward. |
| **Parallel (fan-out/fan-in)** | Run multiple agents concurrently and aggregate results. |
| **Conditional** | Branch orchestration logic based on structured agent output. |
| **Human-in-the-loop** | Pause for external events (approvals, feedback) with optional timeouts. |

### Using agents in orchestrations

Inside an orchestration function, obtain a `DurableAIAgent` via the orchestration context. Each agent gets its own session (created with `CreateSessionAsync` / `create_session`), and you can call the same agent multiple times on the same session to maintain conversation context across sequential invocations.

**C#:**

```csharp
static async Task<string> WritingOrchestration(TaskOrchestrationContext context)
{
    // Get a durable agent reference — works in any host (console app, Azure Functions, etc.)
    DurableAIAgent writer = context.GetAgent("WriterAgent");

    // Create a session to maintain conversation context across multiple calls
    AgentSession session = await writer.CreateSessionAsync();

    // First call: generate an initial draft
    AgentResponse<TextResponse> draft = await writer.RunAsync<TextResponse>(
        message: "Write a concise inspirational sentence about learning.",
        session: session);

    // Second call: refine the draft — the agent sees the full conversation history
    AgentResponse<TextResponse> refined = await writer.RunAsync<TextResponse>(
        message: $"Improve this further while keeping it under 25 words: {draft.Result.Text}",
        session: session);

    return refined.Result.Text;
}
```

**Python:**

```python
def writing_orchestration(context, _):
    agent_ctx = DurableAIAgentOrchestrationContext(context)

    # Get a durable agent reference — works in any host (standalone worker, Azure Functions, etc.)
    writer = agent_ctx.get_agent("WriterAgent")

    # Create a session to maintain conversation context across multiple calls
    session = writer.create_session()

    # First call: generate an initial draft
    draft = yield writer.run(
        messages="Write a concise inspirational sentence about learning.",
        session=session,
    )

    # Second call: refine the draft — the agent sees the full conversation history
    refined = yield writer.run(
        messages=f"Improve this further while keeping it under 25 words: {draft.text}",
        session=session,
    )

    return refined.text
```

> [!IMPORTANT]
> In .NET, `DurableAIAgent.RunAsync<T>` deliberately avoids `ConfigureAwait(false)` because the Durable Task Framework uses a custom synchronization context — all continuations must run on the orchestration thread.

## Streaming and response callbacks

Durable agents do not support true end-to-end streaming because entity operations are request/response. However, **reliable streaming** is supported via response callbacks:

- **`IAgentResponseHandler`** (.NET) or **`AgentResponseCallbackProtocol`** (Python) – Implement this interface to receive streaming updates as the underlying agent generates them (e.g., push tokens to a Redis Stream for client consumption).
- The entity still returns the complete `AgentResponse` after the stream is fully consumed.
- Clients can reconnect and resume reading from a cursor-based stream (e.g., Redis Streams) without losing messages.

See the **Reliable Streaming** samples for a complete implementation using Redis Streams.

## Session TTL (Time-To-Live)

Durable agent sessions support automatic cleanup via configurable TTL. See [Session TTL](durable-agents-ttl.md) for details on configuration, behavior, and best practices.

## Observability

When using the [Durable Task Scheduler](https://learn.microsoft.com/azure/azure-functions/durable/durable-task-scheduler/durable-task-scheduler) as the durable backend, you get built-in observability through its dashboard:

- **Conversation history** – View complete chat history for each agent session.
- **Orchestration visualization** – See multi-agent execution flows, including parallel branches and conditional logic.
- **Performance metrics** – Monitor agent response times, token usage, and orchestration duration.
- **Debugging** – Trace tool invocations and external event handling.

## Samples

- **.NET** – [Console app samples](../../../dotnet/samples/04-hosting/DurableAgents/ConsoleApps/) and [Azure Functions samples](../../../dotnet/samples/04-hosting/DurableAgents/AzureFunctions/) covering single-agent, chaining, concurrency, conditionals, human-in-the-loop, long-running tools, MCP tool exposure, and reliable streaming.
- **Python** – [Durable Task samples](../../../python/samples/04-hosting/durabletask/) covering single-agent, multi-agent, streaming, chaining, concurrency, conditionals, and human-in-the-loop.

## Packages

| Language | Package | Source |
| --- | --- | --- |
| .NET | `Microsoft.Agents.AI.DurableTask` | [`dotnet/src/Microsoft.Agents.AI.DurableTask`](../../../dotnet/src/Microsoft.Agents.AI.DurableTask) |
| .NET | `Microsoft.Agents.AI.Hosting.AzureFunctions` | [`dotnet/src/Microsoft.Agents.AI.Hosting.AzureFunctions`](../../../dotnet/src/Microsoft.Agents.AI.Hosting.AzureFunctions) |
| Python | `agent-framework-durabletask` | [`python/packages/durabletask`](../../../python/packages/durabletask) |
| Python | `agent-framework-azurefunctions` | [`python/packages/azurefunctions`](../../../python/packages/azurefunctions) |

## Further reading

- [Azure Functions (Durable) — Microsoft Learn](https://learn.microsoft.com/agent-framework/integrations/azure-functions)
- [Durable Task Scheduler](https://learn.microsoft.com/azure/azure-functions/durable/durable-task-scheduler/durable-task-scheduler)
- [Durable Entities](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-entities)
- [Session TTL](durable-agents-ttl.md)
