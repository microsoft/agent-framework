# Get Started with Microsoft Agent Framework for C# Developers

## Quickstart

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

## In-memory session storage

`Microsoft.Agents.AI` includes the experimental `InMemoryAgentSessionStore` for local development
and testing; no hosting package is required:

```csharp
using Microsoft.Agents.AI;

AgentSessionStore store = new InMemoryAgentSessionStore();
```

Sessions are stored as serialized snapshots, isolated by `AIAgent.Id` and the complete
`AgentSessionStoreKey`, including every named partition. Each lookup restores an independent session.
Hosts must derive user and tenant partitions from trusted identity data. Concurrent saves to the same
key replace the previous snapshot; coordinate concurrent turns when updates must not be lost.
The store is process-local, has no eviction, and loses sessions on restart. Use a durable store for
production persistence or multiple host instances.

`WithInMemorySessionStore()` registers the core store and retains its optional isolation wrapper.
The existing `Microsoft.Agents.AI.Hosting.InMemoryAgentSessionStore` remains as a compatibility wrapper.
`Microsoft.Agents.AI.Foundry.Hosting.InMemoryAgentSessionStore` shares the core implementation but
preserves Foundry's resolved hosting identity, name fallback, and instance-ID fallback for unnamed agents.
When importing both core and hosting namespaces, qualify the desired store or add a C# type alias to
avoid an ambiguous `InMemoryAgentSessionStore` reference. Custom hosting stores can override
`GetAgentIdentity(AIAgent)` to supply their own stable identity without changing snapshot storage.

## Examples & Samples

- [Getting Started with Agents](./samples/02-agents/Agents): basic agent creation and tool usage
- [Agent Provider Samples](./samples/02-agents/AgentProviders): samples showing different agent providers
- [Workflow Samples](./samples/03-workflows): advanced multi-agent patterns and workflow orchestration

## Agent Framework Documentation

- [Documentation](https://learn.microsoft.com/agent-framework/)
- [Agent Framework Repository](https://github.com/microsoft/agent-framework)
- [Design Documents](../docs/design)
- [Architectural Decision Records](../docs/decisions)
- [MSFT Learn Docs](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview)
