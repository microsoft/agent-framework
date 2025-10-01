# Get Started with Microsoft Agent Framework for C# Developers

## Samples

- [Getting Started with Agents](./samples/GettingStarted/Agents): basic agent creation and tool usage
- [Agent Provider Samples](./samples/GettingStarted/AgentProviders): samples showing different agent providers
- [Workflow Samples](./samples/GettingStarted/Workflows): advanced multi-agent patterns and workflow orchestration

## Quickstart

### Basic Agent - .NET

```c#
using System;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")!;
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME")!;

var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetOpenAIResponseClient(deploymentName)
    .CreateAIAgent(name: "HaikuBot", instructions: "You are an upbeat assistant that writes beautifully.");

Console.WriteLine(await agent.RunAsync("Write a haiku about Microsoft Agent Framework."));
```

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
