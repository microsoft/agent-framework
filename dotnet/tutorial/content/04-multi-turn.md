# Multi-Turn Conversations

**Sample:** `dotnet/samples/01-get-started/03_multi_turn/`

A session object preserves conversation context across multiple `RunAsync` calls. The agent remembers what was said earlier.

## The Complete Program

```csharp
// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with a multi-turn conversation.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

// Invoke the agent with a multi-turn conversation, where the context is preserved in the session object.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));
Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session));

// Invoke the agent with a multi-turn conversation and streaming.
session = await agent.CreateSessionAsync();
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate.", session))
{
    Console.WriteLine(update);
}
await foreach (var update in agent.RunStreamingAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session))
{
    Console.WriteLine(update);
}
```

## How Sessions Work

Without a session, each `RunAsync` call is independent — the agent has no memory of previous messages.

```csharp
// No session — stateless
await agent.RunAsync("Tell me a joke about a pirate.");
await agent.RunAsync("Now tell it in pirate voice."); // ← agent has forgotten the joke
```

With a session, the full message history is accumulated and sent with every request:

```csharp
AgentSession session = await agent.CreateSessionAsync();
await agent.RunAsync("Tell me a joke about a pirate.", session);
await agent.RunAsync("Now tell it in pirate voice.", session); // ← agent remembers the joke
```

Internally, `AgentSession` accumulates a list of `ChatMessage` objects (user messages, assistant responses, tool calls and results). Each new call to `RunAsync` appends to this list and sends the full history to the LLM.

## Session Lifecycle

```csharp
// Create
AgentSession session = await agent.CreateSessionAsync();

// Use (multiple turns)
await agent.RunAsync("message 1", session);
await agent.RunAsync("message 2", session);

// Serialize (for persistence)
JsonElement saved = await agent.SerializeSessionAsync(session);

// Deserialize (restore later)
AgentSession restored = await agent.DeserializeSessionAsync(saved);
await agent.RunAsync("message 3", restored); // ← continues from where we left off
```

Session serialization is covered in depth in the [Memory chapter](./05-memory).

## When to Use Sessions

| Scenario | Use session? |
|---|---|
| Single question/answer | No |
| Chat application | Yes |
| Pipeline where each step is independent | No |
| Interactive assistant with context | Yes |
| Batch processing independent items | No |

## Running the Sample

```bash
cd dotnet/samples/01-get-started/03_multi_turn
dotnet run
```

## Key Takeaways

- `agent.CreateSessionAsync()` creates a new conversation thread
- Pass the session to every `RunAsync` / `RunStreamingAsync` call to maintain context
- Sessions accumulate the full message history
- Sessions serialize to `JsonElement` for persistence and resumption
