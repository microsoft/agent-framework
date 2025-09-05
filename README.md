# Microsoft Agent Framework

## Welcome to the Private Preview of Agent Framework!

You're getting early access to Microsoft's comprehensive multi-language framework for building, orchestrating, and deploying AI agents with support for both .NET and Python implementations. This framework provides everything from simple chat agents to complex multi-agent workflows with graph-based orchestration.

**A few important notes:**
- There currently are not public pypi or nuget packages for the SDKs. In order for the code and samples to work, please clone this repo and run the code here.
- The repo is an active project so make sure to sync regularly.

**We want your feedback!** 
- For bugs, please file a [GitHub issue](https://github.com/microsoft/agent-framework/issues).
- For feedback and suggestions for the team, please fill out [this survey](https://forms.office.com/Pages/ResponsePage.aspx?id=v4j5cvGGr0GRqy180BHbR9huAe5pW55CqgnnimXONJJUMlVMUzdCN1ZGOURXODlBSVJOSkxERVNCNS4u).

**Highlights**
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

### .Net
- [Getting Started with Agents](./dotnet/samples/GettingStarted/Agents): basic agent creation and tool usage
- [Agent Provider Samples](./dotnet/samples/GettingStarted/AgentProviders): samples showing different agent providers
- [Orchestration Samples](./dotnet/samples/GettingStarted/Orchestration): advanced multi-agent patterns

## Agent Framework Documentation

- [Python documentation](./user-documentation-python/README.md)
- [DotNet documentation](./user-documentation-dotnet/README.md)
- [Agent Framework Repository](https://github.com/microsoft/agent-framework)
- [Design Documents](./docs/design)
- [Architectural Decision Records](./docs/decisions)
- Learn docs are coming soon.