# Getting started with Foundry Agents

These samples demonstrate how to use `FoundryAgent` (backed by the **Responses API**) to work with
Microsoft Foundry models directly, without creating server-side agent definitions.

## How these differ from [Foundry Versioned Agents](../FoundryVersionedAgents/README.md)

| | **Foundry Versioned Agents** | **Foundry Agents** |
|---|---|---|
| **Server-side agent** | Yes — agent is created, versioned, and managed in the Foundry service | No — instructions, tools, and options live entirely in your code |
| **Versioning** | Agent versions are immutable; behavior is locked at creation time | No versioning; agent behavior changes when you redeploy code |
| **Lifecycle** | Create → Run → Delete | Instantiate → Run (nothing to clean up) |
| **Backing API** | Foundry Agents API (`GetProjectResponsesClientForAgent`) | Responses API (`GetProjectResponsesClientForModel`) |
| **Type** | `FoundryVersionedAgent` | `FoundryAgent` |

Choose **Foundry Versioned Agents** when you need managed, versioned agent definitions visible in the Foundry portal.
Choose **Foundry Agents** when you want a lightweight, code-first agent with no server-side state.

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and project configured
- Azure CLI installed and authenticated (for Azure credential authentication)

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

Many of the samples default the deployment name to `gpt-4o-mini` when the environment variable is not set.

```csharp
string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? "gpt-4o-mini";

FoundryAgent agent = new(
    endpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential(),
    model: deploymentName,
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");
```

For advanced scenarios (structured output, plugins with DI, etc.), use the options-based constructor and set `ChatOptions.ModelId` explicitly:

```csharp
FoundryAgent agent = new(
    endpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential(),
    options: new ChatClientAgentOptions
    {
        Name = "StructuredAgent",
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = "Extract structured information.",
            ResponseFormat = ChatResponseFormat.ForJsonSchema<MyType>()
        }
    });
```

Some samples require additional environment variables for specific tools (for example, Bing Custom Search, SharePoint, Fabric, and Memory). Refer to each sample's comments for details.

## Samples

|Sample|Description|
|---|---|
|[Basics](./FoundryAgents_Step01_Basics/)|This sample demonstrates how to create and run a basic agent using the Responses API|
|[Multi-turn conversation](./FoundryAgents_Step02_MultiturnConversation/)|This sample demonstrates how to implement a multi-turn conversation using the Responses API|
|[Using function tools](./FoundryAgents_Step03_UsingFunctionTools/)|This sample demonstrates how to use function tools with the Responses API|
|[Using function tools with approvals](./FoundryAgents_Step04_UsingFunctionToolsWithApprovals/)|This sample demonstrates how to use function tools with human-in-the-loop approval|
|[Structured output](./FoundryAgents_Step05_StructuredOutput/)|This sample demonstrates how to use structured output with the Responses API|
|[Persisted conversations](./FoundryAgents_Step06_PersistedConversations/)|This sample demonstrates how to persist and resume conversations|
|[Observability](./FoundryAgents_Step07_Observability/)|This sample demonstrates how to add OpenTelemetry observability|
|[Dependency injection](./FoundryAgents_Step08_DependencyInjection/)|This sample demonstrates how to use dependency injection with a hosted service|
|[Using MCP client as tools](./FoundryAgents_Step09_UsingMcpClientAsTools/)|This sample demonstrates how to use MCP client tools with the Responses API|
|[Using images](./FoundryAgents_Step10_UsingImages/)|This sample demonstrates how to use image multi-modality|
|[Agent as function tool](./FoundryAgents_Step11_AsFunctionTool/)|This sample demonstrates how to use one agent as a function tool for another|
|[Middleware](./FoundryAgents_Step12_Middleware/)|This sample demonstrates multiple middleware layers (PII, guardrails, approvals)|
|[Plugins](./FoundryAgents_Step13_Plugins/)|This sample demonstrates how to use plugins with dependency injection|
|[Code interpreter](./FoundryAgents_Step14_CodeInterpreter/)|This sample demonstrates how to use the code interpreter tool|
|[Computer use](./FoundryAgents_Step15_ComputerUse/)|This sample demonstrates how to use the computer use tool|
|[File search](./FoundryAgents_Step16_FileSearch/)|This sample demonstrates how to use the file search tool|
|[OpenAPI tools](./FoundryAgents_Step17_OpenAPITools/)|This sample demonstrates how to use OpenAPI tools|
|[Bing custom search](./FoundryAgents_Step18_BingCustomSearch/)|This sample demonstrates how to use the Bing Custom Search tool|
|[SharePoint](./FoundryAgents_Step19_SharePoint/)|This sample demonstrates how to use the SharePoint grounding tool|
|[Microsoft Fabric](./FoundryAgents_Step20_MicrosoftFabric/)|This sample demonstrates how to use the Microsoft Fabric tool|
|[Web search](./FoundryAgents_Step21_WebSearch/)|This sample demonstrates how to use the web search tool|
|[Memory search](./FoundryAgents_Step22_MemorySearch/)|This sample demonstrates how to use the memory search tool|
|[Local MCP](./FoundryAgents_Step23_LocalMCP/)|This sample demonstrates how to use a local MCP client with HTTP transport|

## Running the samples from the console

To run the samples, navigate to the sample root and run the desired project, for example:

```powershell
cd dotnet/samples/02-agents/FoundryAgents
dotnet run --project .\FoundryAgents_Step01_Basics
```

## Running the samples from Visual Studio

Open the solution in Visual Studio and set the desired sample project as the startup project. Then, run the project using the built-in debugger or by pressing `F5`.

You will be prompted for any required environment variables if they are not already set.
