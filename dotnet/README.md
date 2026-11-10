# Get Started with Microsoft Agent Framework for C# Developers

## Quickstart

### Building from source

Install the [.NET 11 RC SDK](https://dotnet.microsoft.com/download/dotnet/11.0)
specified in `global.json`. Libraries that support .NET 9 also target .NET 11,
which is a Standard Term Support (STS) release. Existing targets are retained.
The .NET 10 runtime is still required to run .NET 10 tests and samples.

CI builds, packages, and runs unit and integration tests for `net11.0` alongside
the existing targets. Code coverage and sample verification remain on `net10.0`.
When moving to the final .NET 11 release, update `global.json`, the .NET 11
`Microsoft.AspNetCore.TestHost` version in `Directory.Packages.props`, and the SDK
container tags in the format workflow and source-building sample Dockerfiles.
The DevUI project also has a temporary workaround for
[dotnet/sdk#56656](https://github.com/dotnet/sdk/issues/56656) that disables
generation of its Debug browser tools assets when using a .NET 11 RC SDK. Remove
the workaround when the SDK issue is fixed.

### Basic Agent - .NET

```c#
using System.ClientModel.Primitives;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI;
using OpenAI.Responses;

// Use the Azure OpenAI v1 route with the OpenAI SDK (resource root + /openai/v1).
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")!; // e.g. https://YOUR.openai.azure.com/openai/v1/
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME")!;

var agent = new OpenAIClient(
        new BearerTokenPolicy(new AzureCliCredential(), "https://ai.azure.com/.default"),
        new OpenAIClientOptions { Endpoint = new Uri(endpoint) })
    .GetResponsesClient()
    .AsAIAgent(model: deploymentName, name: "HaikuBot", instructions: "You are an upbeat assistant that writes beautifully.");

Console.WriteLine(await agent.RunAsync("Write a haiku about Microsoft Agent Framework."));
```

## Examples & Samples

- [Getting Started with Agents](./samples/02-agents/Agents): basic agent creation and tool usage
- [Agent Provider Samples](./samples/02-agents/AgentProviders): samples showing different agent providers
- [Workflow Samples](./samples/03-workflows): advanced multi-agent patterns and workflow orchestration
- [Hosting guidance](./samples/04-hosting/README.md): authentication, endpoint authorization, and caller isolation across hosting protocols

## Agent Framework Documentation

- [Documentation](https://learn.microsoft.com/agent-framework/)
- [Agent Framework Repository](https://github.com/microsoft/agent-framework)
- [Design Documents](../docs/design)
- [Architectural Decision Records](../docs/decisions)
- [MSFT Learn Docs](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview)
