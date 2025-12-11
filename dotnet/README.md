# Get Started with Microsoft Agent Framework for C# Developers

## Samples

- [Getting Started with Agents](./samples/GettingStarted/Agents): basic agent creation and tool usage
- [Agent Provider Samples](./samples/GettingStarted/AgentProviders): samples showing different agent providers
- [Workflow Samples](./samples/GettingStarted/Workflows): advanced multi-agent patterns and workflow orchestration

## Quickstart

### Basic Agent - .NET

```c#
using System;
using System.ClientModel.Primitives;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")!;
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME")!;

var agent = new OpenAIClient(
    new BearerTokenPolicy(new AzureCliCredential(), "https://ai.azure.com/.default"),
    new OpenAIClientOptions() { Endpoint = new Uri($"{endpoint}/openai/v1") })
    .GetOpenAIResponseClient(deploymentName)
    .CreateAIAgent(name: "HaikuBot", instructions: "You are an upbeat assistant that writes beautifully.");

Console.WriteLine(await agent.RunAsync("Write a haiku about Microsoft Agent Framework."));
```

## Examples & Samples

- [Getting Started with Agents](./samples/GettingStarted/Agents): basic agent creation and tool usage
- [Agent Provider Samples](./samples/GettingStarted/AgentProviders): samples showing different agent providers
- [Workflow Samples](./samples/GettingStarted/Workflows): advanced multi-agent patterns and workflow orchestration

## Agent Framework Documentation

- [Documentation](https://learn.microsoft.com/agent-framework/)
- [Agent Framework Repository](https://github.com/microsoft/agent-framework)
- [Design Documents](../docs/design)
- [Architectural Decision Records](../docs/decisions)
- [MSFT Learn Docs](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview)
