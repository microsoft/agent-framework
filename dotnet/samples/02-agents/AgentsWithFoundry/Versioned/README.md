# Getting started with Foundry Versioned Agents

These samples demonstrate server-side Foundry agent flows using native `AIProjectClient.Agents` APIs and then wrapping the resulting `AgentRecord` or `AgentVersion` with `AIProjectClient.AsAIAgent(...)`.

## Configuration

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

Basic pattern:

```csharp
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AgentVersion version = await aiProjectClient.Agents.CreateAgentVersionAsync(
    "MyAgent",
    new AgentVersionCreationOptions(
        new PromptAgentDefinition(deploymentName)
        {
            Instructions = "You are a helpful assistant."
        }));

ChatClientAgent agent = aiProjectClient.AsAIAgent(version);

await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
```

Unlike the direct Responses samples, this path creates persistent server-side agent resources whose behavior is defined at creation time.

## Prerequisites

- .NET 10 SDK or later
- Foundry project endpoint
- Azure CLI installed and authenticated

## Samples

| Sample | Description |
| --- | --- |
| [Basics](./Agent_Step01.1_Basics/) | Creating and managing Foundry `AgentVersion` resources |
| [Running a simple agent](./Agent_Step01.2_Running/) | Creating and running a basic versioned agent |
| [Multi-turn conversation](./Agent_Step02_MultiturnConversation/) | Multi-turn conversation with a server-side agent |
| [Using function tools](./Agent_Step03_UsingFunctionTools/) | Function tools with a versioned agent |
| [Using function tools with approvals](./Agent_Step04_UsingFunctionToolsWithApprovals/) | Human-in-the-loop approval before function execution |
| [Structured output](./Agent_Step05_StructuredOutput/) | Structured output with JSON schema |
| [Persisted conversations](./Agent_Step06_PersistedConversations/) | Persisting and resuming conversations |
| [Observability](./Agent_Step07_Observability/) | Adding telemetry and tracing |
| [Dependency injection](./Agent_Step08_DependencyInjection/) | Using versioned agents with DI containers |
| [Using MCP client as tools](./Agent_Step09_UsingMcpClientAsTools/) | MCP clients as agent tools |
| [Using images](./Agent_Step10_UsingImages/) | Image multi-modality |
| [Exposing as a function tool](./Agent_Step11_AsFunctionTool/) | Exposing a versioned agent as a function tool |
| [Using middleware](./Agent_Step12_Middleware/) | Middleware pipeline for agents |
| [Using plugins](./Agent_Step13_Plugins/) | Plugin-based tool registration |
| [Code interpreter](./Agent_Step14_CodeInterpreter/) | Code interpreter tool |
| [Computer use](./Agent_Step15_ComputerUse/) | Computer use capabilities |
| [File search](./Agent_Step16_FileSearch/) | File search tool |
| [OpenAPI tools](./Agent_Step17_OpenAPITools/) | OpenAPI tools |
| [Bing Custom Search](./Agent_Step18_BingCustomSearch/) | Bing Custom Search |
| [SharePoint grounding](./Agent_Step19_SharePoint/) | SharePoint grounding |
| [Microsoft Fabric](./Agent_Step20_MicrosoftFabric/) | Microsoft Fabric |
| [Web search](./Agent_Step21_WebSearch/) | Web search |
| [Memory search](./Agent_Step22_MemorySearch/) | Memory search |
| [Local MCP](./Agent_Step23_LocalMCP/) | Local MCP server tools |

## Evaluation Samples

| Sample | Description |
| --- | --- |
| [Red Team Evaluation](./Agent_Evaluations_Step01_RedTeaming/) | Red Teaming service for adversarial attack assessment |
| [Self-Reflection with Groundedness](./Agent_Evaluations_Step02_SelfReflection/) | Self-reflection pattern with groundedness evaluation |

## Running the samples

```powershell
cd dotnet/samples/02-agents/AgentsWithFoundry/Versioned
dotnet run --project .\Agent_Step01.2_Running
```
