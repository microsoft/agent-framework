# Agent Framework Samples

The agent framework samples are designed to help you get started with building AI-powered agents
from various providers.

The Agent Framework supports building agents using various infererence and inference-style services.
All these are supported using the single `ChatClientAgent` class.

The Agent Framework also supports creating proxy agents, that allow accessing remote agents as if they
were local agents. These are supported using various `AIAgent` subclasses.

## Sample Structure

| Folder | Description |
|--------|-------------|
| [`01-get-started/`](./01-get-started/) | Progressive tutorial: hello agent → hosting |
| [`02-agents/`](./02-agents/) | Deep-dive by concept: tools, middleware, providers, orchestrations |
| [`03-workflows/`](./03-workflows/) | Workflow patterns: sequential, concurrent, state, declarative |
| [`04-hosting/`](./04-hosting/) | Deployment: Azure Functions, Durable Tasks, A2A |
| [`05-end-to-end/`](./05-end-to-end/) | Full applications, evaluation, demos |

## Getting Started

Start with `01-get-started/` and work through the numbered files:

1. **[01_hello_agent](./01-get-started/01_hello_agent/Program.cs)** — Create and run your first agent
2. **[02_add_tools](./01-get-started/02_add_tools/Program.cs)** — Add function tools
3. **[03_multi_turn](./01-get-started/03_multi_turn/Program.cs)** — Multi-turn conversations with `AgentSession`
4. **[04_memory](./01-get-started/04_memory/Program.cs)** — Agent memory with `AIContextProvider`
5. **[05_first_workflow](./01-get-started/05_first_workflow/Program.cs)** — Build a workflow with executors and edges
6. **[06_host_your_agent](./01-get-started/06_host_your_agent/Program.cs)** — Host your agent via Azure Functions

## Additional Samples

Some additional samples of note include:

- [Agents](./02-agents/Agents/README.md): Basic steps to get started with the agent framework.
  These samples demonstrate the fundamental concepts and functionalities of the agent framework when using the
  `AIAgent` and can be used with any underlying service that provides an `AIAgent` implementation.
- [Agent Providers](./02-agents/AgentProviders/README.md): Shows how to create an AIAgent instance for a selection of providers.
- [Agent Telemetry](./02-agents/AgentOpenTelemetry/README.md): Demo which showcases the integration of OpenTelemetry with the Microsoft Agent Framework using Azure OpenAI and .NET Aspire Dashboard for telemetry visualization.
- [Durable Agents - Azure Functions](./04-hosting/DurableAgents/AzureFunctions/README.md): Samples for using the Microsoft Agent Framework with Azure Functions via the durable task extension.
- [Durable Agents - Console Apps](./04-hosting/DurableAgents/ConsoleApps/README.md): Samples demonstrating durable agents in console applications.

## Migration from Semantic Kernel

If you are migrating from Semantic Kernel to the Microsoft Agent Framework, the following resources provide guidance and side-by-side examples to help you transition your existing agents, tools, and orchestration patterns. 
The migration samples map Semantic Kernel primitives (such as `ChatCompletionAgent` and Team orchestrations) to their Agent Framework equivalents (such as `ChatClientAgent` and workflow builders). 

For an in-depth migration guide, see the [official migration documentation](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-semantic-kernel).

## Prerequisites

For prerequisites see each set of samples for their specific requirements.
