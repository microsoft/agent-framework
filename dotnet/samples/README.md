# Agent Framework Samples

The agent framework samples are designed to help you get started with building AI-powered agents
from various providers.

The Agent Framework supports building agents using various infererence and inference-style services.
All these are supported using the single `ChatClientAgent` class.

The Agent Framework also supports creating proxy agents, that allow accessing remote agents as if they
were local agents. These are supported using various `AIAgent` subclasses.

## Sample Categories

The samples are subdivided into the following categories:

- [Getting Started - Agents](./GettingStarted/Agents/README.md): Basic steps to get started with the agent framework.
  These samples demonstrate the fundamental concepts and functionalities of the agent framework when using the
  `AIAgent` and can be used with any underlying service that provides an `AIAgent` implementation.
- [Getting Started - Agent Providers](./GettingStarted/AgentProviders/README.md): Shows how to create an AIAgent instance for a selection of providers.
- [Getting Started - Agent Telemetry](./GettingStarted/AgentOpenTelemetry/README.md): Demo which showcases the integration of OpenTelemetry with the Microsoft Agent Framework using Azure OpenAI and .NET Aspire Dashboard for telemetry visualization.
- [Semantic Kernel to Agent Framework Migration](https://github.com/microsoft/semantic-kernel/tree/main/dotnet/samples/AgentFrameworkMigration): For instructions and samples describing how to migrate from Semantic Kernel to Microsoft Agent Framework
- [Azure Functions](./AzureFunctions/README.md): Samples for using the Microsoft Agent Framework with Azure Functions via the durable task extension.

## Prerequisites

For prerequisites see each set of samples for their specific requirements.
