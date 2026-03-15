# Architecture Deep Dive

MAF is built around a small set of core abstractions that compose cleanly together.

## Core Type Hierarchy

```
AIAgent  (abstract)
└── ChatClientAgent  (concrete implementation)
        │
        └── uses IChatClient  (from Microsoft.Extensions.AI)
                └── AzureOpenAIChatClient, OpenAIChatClient, …
```

### `AIAgent`

The abstract base class every agent derives from. It exposes:

```csharp
// Invoke — returns the full response as a string
Task<string> RunAsync(string message, AgentSession? session = null);
Task<string> RunAsync(ChatMessage message, AgentSession? session = null);

// Stream — yields response chunks as they arrive
IAsyncEnumerable<string> RunStreamingAsync(string message, AgentSession? session = null);

// Session management
Task<AgentSession> CreateSessionAsync();
Task<JsonElement> SerializeSessionAsync(AgentSession session);
Task<AgentSession> DeserializeSessionAsync(JsonElement state);

// Service location (dependency injection within the agent)
T? GetService<T>();
```

Agents also carry metadata: `Id`, `Name`, and `Description`.

### `AgentSession`

Represents a single conversation thread. Sessions:

- Hold the message history sent to the LLM
- Carry a `StateBag` — arbitrary serializable key-value pairs
- Are serializable to/from `JsonElement` for persistence

Session objects are passed to every `RunAsync` / `RunStreamingAsync` call to maintain context.

### `ChatClientAgent`

The built-in implementation of `AIAgent`. It wraps any `IChatClient` (the `Microsoft.Extensions.AI` interface) and adds:

- System instructions injection
- Tool/function registration
- `AIContextProvider` pipeline

You never instantiate `ChatClientAgent` directly — the `.AsAIAgent()` extension method creates it for you.

### `AITool` and `AIFunction`

Tools are things the agent can invoke. `AIFunction` is the most common — it wraps a .NET delegate:

```csharp
AIFunction tool = AIFunctionFactory.Create(MyMethod);
```

`AIFunctionFactory.Create` uses reflection to read `[Description]` attributes and generate the JSON schema the LLM needs to call the function.

### `AIContextProvider`

A hook that runs before and after every agent invocation:

```csharp
public abstract class AIContextProvider
{
    // Called before the LLM request — add extra instructions/context
    protected abstract ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, ...);

    // Called after the LLM response — extract and store information
    protected abstract ValueTask StoreAIContextAsync(InvokedContext context, ...);
}
```

Subclass this to build custom memory, user-profile injection, retrieval-augmented generation, etc.

## Package Layout

| Package | Contains |
|---|---|
| `Microsoft.Agents.AI` | `AIAgent`, `AgentSession`, `ChatClientAgent`, extension methods |
| `Microsoft.Agents.AI.Abstractions` | Interfaces and abstract base classes |
| `Microsoft.Agents.AI.Workflows` | `WorkflowBuilder`, `Executor`, `Run` |
| `Microsoft.Agents.AI.Hosting.AzureFunctions` | `ConfigureDurableAgents` |

## External Dependencies

MAF leans heavily on **`Microsoft.Extensions.AI`** — the standard .NET abstraction for AI services:

- `IChatClient` — the universal interface for LLM backends
- `ChatMessage` / `AIContent` — message types
- `FunctionInvokingChatClient` — middleware that handles the function-calling loop

This means any provider that ships an `IChatClient` implementation works with MAF without code changes.

## Design Principles

The AGENTS.md file in the repository states four guiding principles:

1. **DRY** — common logic lives in helpers, not duplicated across samples
2. **Single Responsibility** — each class does one thing
3. **Encapsulation** — implementation details stay private
4. **Strong Typing** — use types to document intent and catch errors early

These principles show up throughout the framework: `AIAgent` is abstract (not a god class), sessions carry typed state, and tools carry typed schemas.
