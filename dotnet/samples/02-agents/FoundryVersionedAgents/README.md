# Getting started with Foundry Versioned Agents

These samples demonstrate how to work with server-side versioned agents in Microsoft Foundry using the `FoundryVersionedAgent` class.

Unlike `FoundryAgent` (which uses the Responses API directly), `FoundryVersionedAgent` creates and manages agent definitions
that are versioned and persisted in the Foundry service. Agent behavior (instructions, tools, options) is locked at creation time.

## Configuration

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

Many creation samples default the deployment name to `gpt-4o-mini` when the environment variable is not set. Retrieval-only flows such as `GetAIAgentAsync(...)` do not require a model once the agent already exists.

```csharp
string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? "gpt-4o-mini";

FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(
    endpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential(),
    name: "MyAgent",
    model: deploymentName,
    instructions: "You are a helpful assistant.");

await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
```

For a lightweight, code-first alternative that uses the Responses API directly (no server-side agent creation), see [Foundry Agents](../FoundryAgents/README.md).

## Agent Versioning and Static Definitions

Agents have **versions** and their definitions are established at creation time. The agent's configuration — including instructions, tools, and options — is fixed when the agent version is created.

> [!IMPORTANT]
> Agent versions are static and strictly adhere to their original definition. Any attempt to provide or override tools, instructions, or options during an agent run will be ignored by the agent. All agent behavior must be defined at agent creation time.

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and project configured
- Azure CLI installed and authenticated (`az login`)

## Samples

|Sample|Description|
|---|---|
|[Basics](./FoundryVersionedAgents_Step01.1_Basics/)|Creating and managing AI agents with versioning|
|[Running a simple agent](./FoundryVersionedAgents_Step01.2_Running/)|Creating and running a basic versioned agent|
|[Multi-turn conversation](./FoundryVersionedAgents_Step02_MultiturnConversation/)|Multi-turn conversation using `CreateConversationSessionAsync`|
|[Using function tools](./FoundryVersionedAgents_Step03_UsingFunctionTools/)|Function tools with a versioned agent|
|[Using function tools with approvals](./FoundryVersionedAgents_Step04_UsingFunctionToolsWithApprovals/)|Human-in-the-loop approval before function execution|
|[Structured output](./FoundryVersionedAgents_Step05_StructuredOutput/)|Structured output with JSON schema|
|[Persisted conversations](./FoundryVersionedAgents_Step06_PersistedConversations/)|Persisting and resuming conversations|
|[Observability](./FoundryVersionedAgents_Step07_Observability/)|Adding telemetry and tracing|
|[Dependency injection](./FoundryVersionedAgents_Step08_DependencyInjection/)|Using `FoundryVersionedAgent` with DI containers|
|[Using MCP client as tools](./FoundryVersionedAgents_Step09_UsingMcpClientAsTools/)|MCP clients as agent tools|
|[Using images](./FoundryVersionedAgents_Step10_UsingImages/)|Image multi-modality|
|[Exposing as a function tool](./FoundryVersionedAgents_Step11_AsFunctionTool/)|Exposing a versioned agent as a function tool|
|[Using middleware](./FoundryVersionedAgents_Step12_Middleware/)|Middleware pipeline for agents|
|[Using plugins](./FoundryVersionedAgents_Step13_Plugins/)|Plugin-based tool registration|
|[Code interpreter](./FoundryVersionedAgents_Step14_CodeInterpreter/)|Code interpreter tool via `FoundryAITool.CreateCodeInterpreterTool`|
|[Computer use](./FoundryVersionedAgents_Step15_ComputerUse/)|Computer use capabilities via `FoundryAITool.CreateComputerTool`|
|[File search](./FoundryVersionedAgents_Step16_FileSearch/)|File search tool via `FoundryAITool.CreateFileSearchTool`|
|[OpenAPI tools](./FoundryVersionedAgents_Step17_OpenAPITools/)|OpenAPI tools via `FoundryAITool.CreateOpenApiTool`|
|[Bing Custom Search](./FoundryVersionedAgents_Step18_BingCustomSearch/)|Bing Custom Search via `FoundryAITool.CreateBingCustomSearchTool`|
|[SharePoint grounding](./FoundryVersionedAgents_Step19_SharePoint/)|SharePoint grounding via `FoundryAITool.CreateSharepointTool`|
|[Microsoft Fabric](./FoundryVersionedAgents_Step20_MicrosoftFabric/)|Microsoft Fabric via `FoundryAITool.CreateMicrosoftFabricTool`|
|[Web search](./FoundryVersionedAgents_Step21_WebSearch/)|Web search via `FoundryAITool.CreateWebSearchTool`|
|[Memory search](./FoundryVersionedAgents_Step22_MemorySearch/)|Memory search tool|
|[Local MCP](./FoundryVersionedAgents_Step23_LocalMCP/)|Local MCP server tools|

## Evaluation Samples

|Sample|Description|
|---|---|
|[Red Team Evaluation](./FoundryVersionedAgents_Evaluations_Step01_RedTeaming/)|Red Teaming service for adversarial attack assessment|
|[Self-Reflection with Groundedness](./FoundryVersionedAgents_Evaluations_Step02_SelfReflection/)|Self-reflection pattern with groundedness evaluation|

## Running the samples

```powershell
cd dotnet/samples/02-agents/FoundryVersionedAgents
dotnet run --project .\FoundryVersionedAgents_Step01.2_Running
```
