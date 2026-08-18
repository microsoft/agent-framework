# Get Started with Microsoft Agent Framework for C# Developers

## Quickstart

### Basic Agent - .NET

```c#
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")!;
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME")!;

var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetResponsesClient(deploymentName)
    .AsAIAgent(name: "HaikuBot", instructions: "You are an upbeat assistant that writes beautifully.");

Console.WriteLine(await agent.RunAsync("Write a haiku about Microsoft Agent Framework."));
```

## Examples & Samples

- [Getting Started with Agents](./samples/02-agents/Agents): basic agent creation and tool usage
- [Agent Provider Samples](./samples/02-agents/AgentProviders): samples showing different agent providers
- [Workflow Samples](./samples/03-workflows): advanced multi-agent patterns and workflow orchestration

## Feature-usage telemetry

Agent Framework records coarse, process-lifetime feature usage in a transparent
128-bit mask. On eligible Foundry and Azure OpenAI requests made through Agent
Framework wrappers, the current mask is appended to the existing User-Agent as
`(feat=v1.<hex>)`.

- A bit means that a registered feature was observed at least once in the
  process. Repeated requests are not additional feature uses and must not be
  interpreted as request, agent, user, tenant, or invocation counts.
- No prompts, payloads, model/deployment names, URLs, identifiers, arguments, or
  customer-defined names are encoded.
- Caller-owned Foundry `AIProjectClient` instances and custom transports are
  stamped only when the request URI visible to the policy is an approved Foundry
  HTTPS origin.
- Azure OpenAI Chat and Responses clients adapted with `AsAIAgent` add the
  `agent-framework-dotnet/<version>` User-Agent segment and stamp the feature
  token for HTTPS endpoints under `cognitiveservices.azure.com`,
  `openai.azure.com`, or `services.ai.azure.com`.
- Direct OpenAI, custom OpenAI-compatible endpoints, and other third-party
  clients remain unstamped.
- Set `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED=true` (or `1`) before process
  startup to disable feature collection and the feature comment while retaining
  the base `agent-framework-dotnet/{version}` User-Agent.

See [ADR-0033](../docs/decisions/0033-feature-usage-bitmask-user-agent.md),
[SPEC-004](../docs/specs/004-feature-usage-telemetry.md), and the
[public bit registry](../docs/specs/feature-usage-bit-registry.md) for the
interpretation and allocation contract.

## Agent Framework Documentation

- [Documentation](https://learn.microsoft.com/agent-framework/)
- [Agent Framework Repository](https://github.com/microsoft/agent-framework)
- [Design Documents](../docs/design)
- [Architectural Decision Records](../docs/decisions)
- [MSFT Learn Docs](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview)
