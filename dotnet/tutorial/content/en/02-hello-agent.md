# Hello Agent

**Sample:** `dotnet/samples/01-get-started/01_hello_agent/`

This is the simplest possible MAF agent: a single file that creates an agent, asks it to tell a joke, then does the same with streaming.

## The Complete Program

```csharp
// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with OpenAI as the backend.

using Microsoft.Agents.AI;
using OpenAI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

// Invoke the agent with streaming support.
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}
```

## Step-by-Step Breakdown

### 1. Read configuration from environment

```csharp
var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";
```

MAF follows the convention of reading secrets from environment variables — never hardcoded.

### 2. Build the agent

```csharp
AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");
```

Three chained calls:

| Call | What it does |
|---|---|
| `new OpenAIClient(apiKey)` | Creates the OpenAI connection using your API key |
| `.GetChatClient(model)` | Gets a `ChatClient` for the named model |
| `.AsAIAgent(...)` | Wraps it in a `ChatClientAgent` (implements `AIAgent`) |

The `instructions` parameter becomes the system prompt. The `name` is metadata — useful for logging and multi-agent workflows.

### 3. Non-streaming invocation

```csharp
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
```

`RunAsync` collects the entire response before returning. Use this when you need the complete answer before proceeding.

### 4. Streaming invocation

```csharp
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}
```

`RunStreamingAsync` returns `IAsyncEnumerable<string>`. Each `update` is a chunk of the response as it streams from the model. Use this for interactive UIs where you want to show output progressively.

## Running the Sample

```bash
cd dotnet/samples/01-get-started/01_hello_agent
dotnet run
```

## Key Takeaways

- `AIAgent` is the core abstraction — all agents implement it
- `.AsAIAgent()` is the entry point — wrap any `IChatClient` to get a full agent
- `RunAsync` and `RunStreamingAsync` are the two invocation modes
- No session = stateless; each call is independent
