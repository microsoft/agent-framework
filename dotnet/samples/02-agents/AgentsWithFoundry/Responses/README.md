# Getting started with Foundry Agents

These samples demonstrate the direct Responses path in Azure AI Foundry using `AIProjectClient.AsAIAgent(...)`.

This path is code-first:

- no server-side agent definition is created
- model, instructions, tools, and options are supplied from your code
- the public agent type stays `ChatClientAgent`

## How these differ from [Foundry Versioned Agents](../Versioned/README.md)

|  | Foundry Versioned Agents | Foundry Agents |
| --- | --- | --- |
| Server-side agent | Yes | No |
| Versioning | `AgentVersion` resources are created in Foundry | No server-side versioning |
| Lifecycle | Create -> Run -> Delete | Construct -> Run |
| Primary API | `AIProjectClient.Agents` + `AsAIAgent(...)` | `AIProjectClient.AsAIAgent(...)` |
| Public agent type | `ChatClientAgent` | `ChatClientAgent` |

## Prerequisites

- .NET 10 SDK or later
- Foundry project endpoint
- Azure CLI installed and authenticated

Set:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

Basic construction:

```csharp
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

ChatClientAgent agent = aiProjectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");
```

Some samples require extra tool-specific environment variables. See each sample for details.

## Samples

| Sample | Description |
| --- | --- |
| [Basics](./ChatClientAgents_Step01_Basics/) | Create and run a direct Responses agent |
| [Multi-turn conversation](./ChatClientAgents_Step02_MultiturnConversation/) | Persist a conversation explicitly and reuse the session |
| [Using function tools](./ChatClientAgents_Step03_UsingFunctionTools/) | Function tools with the direct Responses path |
| [Using function tools with approvals](./ChatClientAgents_Step04_UsingFunctionToolsWithApprovals/) | Human-in-the-loop approval before function execution |
| [Structured output](./ChatClientAgents_Step05_StructuredOutput/) | Structured output with JSON schema |
| [Persisted conversations](./ChatClientAgents_Step06_PersistedConversations/) | Persisting and resuming conversations |
| [Observability](./ChatClientAgents_Step07_Observability/) | Adding OpenTelemetry observability |
| [Dependency injection](./ChatClientAgents_Step08_DependencyInjection/) | Using DI with a hosted service |
| [Using MCP client as tools](./ChatClientAgents_Step09_UsingMcpClientAsTools/) | MCP client tools |
| [Using images](./ChatClientAgents_Step10_UsingImages/) | Image multi-modality |
| [Agent as function tool](./ChatClientAgents_Step11_AsFunctionTool/) | Use one agent as a function tool for another |
| [Middleware](./ChatClientAgents_Step12_Middleware/) | Multiple middleware layers |
| [Plugins](./ChatClientAgents_Step13_Plugins/) | Plugins with dependency injection |
| [Code interpreter](./ChatClientAgents_Step14_CodeInterpreter/) | Code interpreter tool |
| [Computer use](./ChatClientAgents_Step15_ComputerUse/) | Computer use tool |
| [File search](./ChatClientAgents_Step16_FileSearch/) | File search tool |
| [OpenAPI tools](./ChatClientAgents_Step17_OpenAPITools/) | OpenAPI tools |
| [Bing custom search](./ChatClientAgents_Step18_BingCustomSearch/) | Bing Custom Search tool |
| [SharePoint](./ChatClientAgents_Step19_SharePoint/) | SharePoint grounding tool |
| [Microsoft Fabric](./ChatClientAgents_Step20_MicrosoftFabric/) | Microsoft Fabric tool |
| [Web search](./ChatClientAgents_Step21_WebSearch/) | Web search tool |
| [Memory search](./ChatClientAgents_Step22_MemorySearch/) | Memory search tool |
| [Local MCP](./ChatClientAgents_Step23_LocalMCP/) | Local MCP client with HTTP transport |

## Running the samples

```powershell
cd dotnet/samples/02-agents/ChatClientAgents
dotnet run --project .\ChatClientAgents_Step01_Basics
```
