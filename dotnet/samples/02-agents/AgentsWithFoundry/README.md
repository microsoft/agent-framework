# Getting started with Foundry Agents

These samples demonstrate how to use Microsoft Foundry with Agent Framework.

## Quick start

The simplest way to create a Foundry agent is using the `FoundryAgent` type directly:

```csharp
FoundryAgent agent = new(
    new Uri(endpoint),
    new AzureCliCredential(),
    model: "gpt-5.4-mini",
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
```

Or using the `AIProjectClient.AsAIAgent(...)` extensions:

```csharp
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

FoundryAgent agent = aiProjectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");
```

## Prerequisites

- .NET 10 SDK or later
- Foundry project endpoint
- Azure CLI installed and authenticated

Set:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
```

Some samples require extra tool-specific environment variables. See each sample for details.

## Samples

| Sample | Description |
| --- | --- |
| [FoundryAgent lifecycle](./Agent_Step00_FoundryAgentLifecycle/) | Create a FoundryAgent directly with endpoint and credentials |
| [Basics (Responses API)](./Agent_Step01_Basics/) | Create and run an agent using AsAIAgent extensions |
| [Multi-turn conversation](./Agent_Step02.1_MultiturnConversation/) | Multi-turn using sessions and response ID chaining |
| [Multi-turn with server conversations](./Agent_Step02.2_MultiturnWithServerConversations/) | Server-side conversations visible in Foundry UI |
| [Using function tools](./Agent_Step03_UsingFunctionTools/) | Function tools |
| [Function tools with approvals](./Agent_Step04_UsingFunctionToolsWithApprovals/) | Human-in-the-loop approval |
| [Structured output](./Agent_Step05_StructuredOutput/) | Structured output with JSON schema |
| [Persisted conversations](./Agent_Step06_PersistedConversations/) | Persisting and resuming conversations |
| [Observability](./Agent_Step07_Observability/) | OpenTelemetry observability |
| [Dependency injection](./Agent_Step08_DependencyInjection/) | DI with a hosted service |
| [Using MCP client as tools](./Agent_Step09_UsingMcpClientAsTools/) | MCP client tools |
| [Using images](./Agent_Step10_UsingImages/) | Image multi-modality |
| [Agent as function tool](./Agent_Step11_AsFunctionTool/) | Agent as a function tool for another |
| [Middleware](./Agent_Step12_Middleware/) | Multiple middleware layers |
| [Plugins](./Agent_Step13_Plugins/) | Plugins with dependency injection |
| [Code interpreter](./Agent_Step14_CodeInterpreter/) | Code interpreter tool |
| [Computer use](./Agent_Step15_ComputerUse/) | Computer use tool |
| [File search](./Agent_Step16_FileSearch/) | File search tool |
| [OpenAPI tools](./Agent_Step17_OpenAPITools/) | OpenAPI tools |
| [Bing custom search](./Agent_Step18_BingCustomSearch/) | Bing Custom Search tool |
| [SharePoint](./Agent_Step19_SharePoint/) | SharePoint grounding tool |
| [Microsoft Fabric](./Agent_Step20_MicrosoftFabric/) | Microsoft Fabric tool |
| [Web search](./Agent_Step21_WebSearch/) | Web search tool |
| [Memory search](./Agent_Step22_MemorySearch/) | Memory search tool |
| [Local MCP](./Agent_Step23_LocalMCP/) | Local MCP client with HTTP transport |

## Running the samples

```powershell
cd dotnet/samples/02-agents/AgentsWithFoundry
dotnet run --project .\FoundryAgent_Step01
```