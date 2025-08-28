# Microsoft Agent Framework Agent Types

The Microsoft Agent Framework provides support for several types of agents to accommodate different use cases and requirements.

All agents are derived from a common base class, `AIAgent`, which provides a consistent interface for all agent types. This allows for building common, agent agnostic, higher level functionality such as multi-agent orchestrations.

Let's dive into each agent type in more detail.

## Simple agents based on inference services

The agent framework makes it easy to create simple agents based on many different inference services.
Any inference service that provides a ChatClient implementation can be used to build these agents.

These agents support a wide range of functionality out of the box:

1. Function calling
1. Multi-turn conversations with local chat history management or service provided chat history management
1. Custom service provided tools (e.g. MCP, Code Execution)
1. Structured output

To create one of these agents, simply construct a `ChatClientAgent` using the ChatClient implementation of your choice.


## Complex custom agents

It is also possible to create fully custom agents, that are not just wrappers around a ChatClient.
The agent framework provides the `AIAgent` base type, which when subclassed allows for complete control over the agent's behavior and capabilities.

## Remote agents

The agent framework provides out of the box `AIAgent` subclasses for common service hosted agent protocols,
such as A2A.

## Pre-built agents

To be added.

