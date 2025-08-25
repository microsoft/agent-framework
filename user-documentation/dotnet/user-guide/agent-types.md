# Microsoft Agent Framework for .NET Agent Types

The Microsoft Agent Framework for .NET provides support for several types of agents to accommodate different use cases and requirements.

All agents are derived from a common base class, `AIAgent`, which provides a consistent interface for all agent types. This allows for building common, agent agnostic, higher level functionality such as multi-agent orchestrations.

Let's dive into each agent type in more detail.

## Simple custom agents based on inference services

The agent framework makes it easy to create simple custom agents based on many different inference services.
Any inference service that provides a `Microsoft.Extensions.AI.IChatClient` implementation can be used to build these agents.

These agents support a wide range of functionality:

1. Function calling
1. Multi-turn conversations with local chat history management or service provided chat history management
1. Custom service provided tools (e.g. MCP, Code Execution)
1. Structured output

To create one of these agents, simply construct a `ChatClientAgent` using the `IChatClient` implementation of your choice:

```csharp
using Microsoft.Extensions.AI;

var agent = new ChatClientAgent(chatClient, instructions: "You are a helpful asssistant");
```

For examples on how to construct `ChatClientAgents` with various `IChatClient` implementations, see the [Agent setup samples](../../../dotnet/samples/AgentSetup).

## Complex custom agents

To be added.

## Remote agents

To be added.

## Pre-built agents

To be added.
