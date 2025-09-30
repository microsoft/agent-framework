![Microsoft Agent Framework](docs/assets/readme-banner.png)

# Welcome to Microsoft Agent Framework!
[![Microsoft Azure AI Foundry Discord](https://dcbadge.limes.pink/api/server/b5zjErwbQM)](https://discord.gg/b5zjErwbQM)

Welcome to Microsoft's comprehensive multi-language framework for building, orchestrating, and deploying AI agents with support for both .NET and Python implementations. This framework provides everything from simple chat agents to complex multi-agent workflows with graph-based orchestration.

## 📋 Getting Started

**Quick Installation:**

- **Python**: `pip install agent-framework`
- **.NET**: `dotnet add package Microsoft.Agents.AI`

**Getting started documentation:**

- **[Quick Start Guide](https://learn.microsoft.com/agent-framework/tutorials/quick-start)** - Simple getting started instructions
- **[Tutorials](https://learn.microsoft.com/agent-framework/tutorials/overview)** - Step by step tutorials

### ✨ **Highlights**

- **Graph-based Workflows**: Connect agents and deterministic functions using data flows with streaming, checkpointing, human-in-the-loop, and time-travel capabilities
  - [Python workflows](./python/samples/getting_started/workflow/) | [.NET workflows](./dotnet/samples/GettingStarted/Workflows/)
- **AF Labs**: Experimental packages for cutting-edge features including benchmarking, reinforcement learning, and research initiatives
  - [Labs directory](./python/packages/lab/)
- **DevUI**: Interactive developer UI for agent development, testing, and debugging workflows
  - [DevUI package](./python/packages/devui/)
- **Python and C#/.NET Support**: Full framework support for both Python and C#/.NET implementations with consistent APIs
  - [Python packages](./python/packages/) | [.NET source](./dotnet/src/)
- **Observability**: Built-in OpenTelemetry integration for distributed tracing, monitoring, and debugging
  - [Python observability](./python/samples/getting_started/workflow/observability/) | [.NET telemetry](./dotnet/samples/GettingStarted/AgentOpenTelemetry/)
- **Multiple Agent Provider Support**: Support for various LLM providers with more being added continuously
  - [Python examples](./python/samples/getting_started/agents/) | [.NET examples](./dotnet/samples/GettingStarted/AgentProviders/)
- **Middleware**: Flexible middleware system for request/response processing, exception handling, and custom pipelines
  - [Python middleware](./python/samples/getting_started/middleware/) | [.NET middleware](./dotnet/samples/GettingStarted/Agents/Agent_Step14_Middleware/)

### 💬 **We want your feedback!**

- For bugs, please file a [GitHub issue](https://github.com/microsoft/agent-framework/issues).

## More Examples & Samples

### Python

- [Getting Started with Agents](./python/samples/getting_started/agents): basic agent creation and tool usage
- [Chat Client Examples](./python/samples/getting_started/chat_client): direct chat client usage patterns
- [Getting Started with Workflows](./python/samples/getting_started/workflows): basic workflow creation and integration with agents

### .NET

- [Getting Started with Agents](./dotnet/samples/GettingStarted/Agents): basic agent creation and tool usage
- [Agent Provider Samples](./dotnet/samples/GettingStarted/AgentProviders): samples showing different agent providers
- [Workflow Samples](./dotnet/samples/GettingStarted/Workflows): advanced multi-agent patterns and workflow orchestration

## Agent Framework Documentation

- [Documentation](https://learn.microsoft.com/agent-framework/)
- [Agent Framework Repository](https://github.com/microsoft/agent-framework)
- [Design Documents](./docs/design)
- [Architectural Decision Records](./docs/decisions)
- [MSFT Learn Docs](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview)
