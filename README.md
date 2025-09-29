# Microsoft Agent Framework

## Welcome to the Private Preview of Agent Framework!

You're getting early access to Microsoft's comprehensive multi-language framework for building, orchestrating, and deploying AI agents with support for both .NET and Python implementations. This framework provides everything from simple chat agents to complex multi-agent workflows with graph-based orchestration.

### 📋 Important Setup Information
**Package Availability:** Public PyPI and NuGet packages are not yet available. You have two options:

**Option 1: Run samples directly from this repository (no package installation needed)**
- Clone this repository
- For .NET: Run samples with `dotnet run` from any sample directory (e.g., `dotnet/samples/GettingStarted/Agents/Agent_Step01_Running`)
- For Python: Run samples from any sample directory (e.g., [`python/samples/getting_started/minimal_sample.py`](python/samples/getting_started/minimal_sample.py)) after setting up the local dev environment following this [guide](python/DEV_SETUP.md).

**Option 2: Install packages in your own project**
- **[.NET Getting Started Guide](./user-documentation-dotnet/getting-started/README.md)** - Instructions for using nightly packages
- **[Python Package Installation Guide](./user-documentation-python/getting-started/package_installation.md)** - Install packages directly from GitHub

**Stay Updated:** This is an active project - sync your local repository regularly to get the latest updates.

### 💬 **We want your feedback!** 
- For bugs, please file a [GitHub issue](https://github.com/microsoft/agent-framework/issues).
- For feedback and suggestions for the team, please fill out [this survey](https://forms.office.com/Pages/ResponsePage.aspx?id=v4j5cvGGr0GRqy180BHbR9huAe5pW55CqgnnimXONJJUMlVMUzdCN1ZGOURXODlBSVJOSkxERVNCNS4u).

### ✨ **Highlights**
- Flexible Agent Framework: build, orchestrate, and deploy AI agents and workflows
- Multi-Agent Orchestration: group chat, sequential, concurrent, and handoff patterns
- Graph-based Workflows: connect agents and deterministic functions using data flows with streaming, checkpointing, time-travel, and Human-in-the-loop.
- Plugin Ecosystem: extend with native functions, OpenAPI, Model Context Protocol (MCP), and more
- LLM Support: OpenAI, Azure OpenAI, Azure AI Foundry, and more
- Runtime Support: in-process and distributed agent execution
- Multimodal: text, vision, and function calling
- Cross-Platform: .NET and Python implementations

Below are the basics for each language implementation. For more details on python see [here](./python/README.md) and for .NET see [here](./dotnet/README.md).

## More Examples & Samples

### Python
- [Getting Started with Agents](./python/samples/getting_started/agents): basic agent creation and tool usage
- [Chat Client Examples](./python/samples/getting_started/chat_client): direct chat client usage patterns
- [Azure Integration](./python/packages/azure): Azure OpenAI and AI Foundry integration
- [Getting Started with Workflows](./python/samples/getting_started/workflow): basic workflow creation and integration with agents

### .NET
- [Getting Started with Agents](./dotnet/samples/GettingStarted/Agents): basic agent creation and tool usage
- [Agent Provider Samples](./dotnet/samples/GettingStarted/AgentProviders): samples showing different agent providers
- [Orchestration Samples](./dotnet/samples/GettingStarted/AgentOrchestration): advanced multi-agent patterns

## Agent Framework Documentation

- [Python documentation](./user-documentation-python/README.md)
- [DotNet documentation](./user-documentation-dotnet/README.md)
- [Agent Framework Repository](https://github.com/microsoft/agent-framework)
- [Design Documents](./docs/design)
- [Architectural Decision Records](./docs/decisions)
- Learn docs are coming soon.
