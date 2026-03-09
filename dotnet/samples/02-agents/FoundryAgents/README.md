# Getting started with Foundry Response Agents

These samples demonstrate how to use the `FoundryAgent` (backed by the **Responses API**) to work with
Microsoft Foundry models directly, without creating server-side agent definitions.

## How these differ from [Foundry Versioned Agents](../FoundryVersionedAgents/README.md)

| | **Foundry Versioned Agents** | **Foundry Agents** |
|---|---|---|
| **Server-side agent** | Yes — agent is created, versioned, and managed in the Foundry service | No — instructions, tools, and options live entirely in your code |
| **Versioning** | Agent versions are immutable; behavior is locked at creation time | No versioning; agent behavior changes when you redeploy code |
| **Lifecycle** | Create → Run → Delete | Instantiate → Run (nothing to clean up) |
| **Backing API** | Foundry Agents API (`GetProjectResponsesClientForAgent`) | Responses API (`GetProjectResponsesClientForModel`) |
| **Type** | `AIAgent` via `AIProjectClient.CreateAIAgentAsync` | `FoundryAgent` (wraps `ChatClientAgent` internally) |

Choose **Foundry Agents** when you need managed, versioned agent definitions visible in the Foundry portal.
Choose **Foundry Response Agents** when you want a lightweight, code-first agent with no server-side state.

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

The `FoundryAgent` auto-discovers these environment variables at construction time and uses `DefaultAzureCredential` for authentication. This means most samples require **no endpoint or credential code** — just set the environment variables and go:

```csharp
// That's it! Endpoint, model, and credential are resolved automatically.
FoundryAgent agent = new(
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");
```

For advanced scenarios (structured output, plugins with DI, etc.), use the options-based constructor:

```csharp
FoundryAgent agent = new(
    options: new ChatClientAgentOptions
    {
        Name = "StructuredAgent",
        ChatOptions = new()
        {
            Instructions = "Extract structured information.",
            ResponseFormat = ChatResponseFormat.ForJsonSchema<MyType>()
        }
    });
```

If you need full control, explicit constructors are also available:

```csharp
FoundryAgent agent = new(
    endpoint: new Uri("https://..."),
    tokenProvider: new DefaultAzureCredential(),
    model: "gpt-4o-mini",
    instructions: "...",
    name: "...");
```

Some samples require additional environment variables for specific tools (e.g., Bing Custom Search, SharePoint, Fabric, Memory). Refer to each sample's comments for details.

## Samples

|Sample|Description|
|---|---|
|[Basics](./FoundryAgentsRAPI_Step01_Basics/)|This sample demonstrates how to create and run a basic agent using the Responses API|
|[Multi-turn conversation](./FoundryAgentsRAPI_Step02_MultiturnConversation/)|This sample demonstrates how to implement a multi-turn conversation using the Responses API|
|[Using function tools](./FoundryAgentsRAPI_Step03_UsingFunctionTools/)|This sample demonstrates how to use function tools with the Responses API|
|[Using function tools with approvals](./FoundryAgentsRAPI_Step04_UsingFunctionToolsWithApprovals/)|This sample demonstrates how to use function tools with human-in-the-loop approval|
|[Structured output](./FoundryAgentsRAPI_Step05_StructuredOutput/)|This sample demonstrates how to use structured output with the Responses API|
|[Persisted conversations](./FoundryAgentsRAPI_Step06_PersistedConversations/)|This sample demonstrates how to persist and resume conversations|
|[Observability](./FoundryAgentsRAPI_Step07_Observability/)|This sample demonstrates how to add OpenTelemetry observability|
|[Dependency injection](./FoundryAgentsRAPI_Step08_DependencyInjection/)|This sample demonstrates how to use dependency injection with a hosted service|
|[Using images](./FoundryAgentsRAPI_Step10_UsingImages/)|This sample demonstrates how to use image multi-modality|
|[Agent as function tool](./FoundryAgentsRAPI_Step11_AsFunctionTool/)|This sample demonstrates how to use one agent as a function tool for another|
|[Middleware](./FoundryAgentsRAPI_Step12_Middleware/)|This sample demonstrates multiple middleware layers (PII, guardrails, approvals)|
|[Using MCP client as tools](./FoundryAgentsRAPI_Step09_UsingMcpClientAsTools/)|This sample demonstrates how to use MCP client tools with the Responses API|
|[Plugins](./FoundryAgentsRAPI_Step13_Plugins/)|This sample demonstrates how to use plugins with dependency injection|
|[Code interpreter](./FoundryAgentsRAPI_Step14_CodeInterpreter/)|This sample demonstrates how to use the code interpreter tool|
|[Computer use](./FoundryAgentsRAPI_Step15_ComputerUse/)|This sample demonstrates how to use the computer use tool|
|[File search](./FoundryAgentsRAPI_Step16_FileSearch/)|This sample demonstrates how to use the file search tool|
|[OpenAPI tools](./FoundryAgentsRAPI_Step17_OpenAPITools/)|This sample demonstrates how to use OpenAPI tools|
|[Bing custom search](./FoundryAgentsRAPI_Step18_BingCustomSearch/)|This sample demonstrates how to use the Bing Custom Search tool|
|[SharePoint](./FoundryAgentsRAPI_Step19_SharePoint/)|This sample demonstrates how to use the SharePoint grounding tool|
|[Microsoft Fabric](./FoundryAgentsRAPI_Step20_MicrosoftFabric/)|This sample demonstrates how to use the Microsoft Fabric tool|
|[Web search](./FoundryAgentsRAPI_Step21_WebSearch/)|This sample demonstrates how to use the web search tool|
|[Memory search](./FoundryAgentsRAPI_Step22_MemorySearch/)|This sample demonstrates how to use the memory search tool|
|[Local MCP](./FoundryAgentsRAPI_Step23_LocalMCP/)|This sample demonstrates how to use a local MCP client with HTTP transport|

## Running the samples from the console

To run the samples, navigate to the desired sample directory, e.g.

```powershell
cd FoundryAgentsRAPI_Step01_Basics
```

Ensure the following environment variables are set:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

Execute the following command to build the sample:

```powershell
dotnet build
```

Execute the following command to run the sample:

```powershell
dotnet run --no-build
```

Or just build and run in one step:

```powershell
dotnet run
```

## Running the samples from Visual Studio

Open the solution in Visual Studio and set the desired sample project as the startup project. Then, run the project using the built-in debugger or by pressing `F5`.

You will be prompted for any required environment variables if they are not already set.
