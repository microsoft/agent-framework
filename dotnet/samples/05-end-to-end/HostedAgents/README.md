# Hosted Agent Samples

These samples demonstrate how to build and host AI agents using the [Azure AI AgentServer SDK](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.agentserver.agentframework-readme). Each sample can be run locally and deployed to Microsoft Foundry as a hosted agent.

## Samples

| Sample | Description |
|--------|-------------|
| [`AgentWithLocalTools`](./AgentWithLocalTools/) | Local C# function tool execution (Seattle hotel search) |
| [`AgentThreadAndHITL`](./AgentThreadAndHITL/) | Human-in-the-loop with `ApprovalRequiredAIFunction` and thread persistence |
| [`AgentWithHostedMCP`](./AgentWithHostedMCP/) | Hosted MCP server tool (Microsoft Learn search) |
| [`AgentWithTextSearchRag`](./AgentWithTextSearchRag/) | RAG with `TextSearchProvider` (Contoso Outdoors) |
| [`AgentsInWorkflows`](./AgentsInWorkflows/) | Sequential workflow pipeline (translation chain) |
| [`FoundryMultiAgent`](./FoundryMultiAgent/) | Multi-agent Writer-Reviewer workflow using `AIProjectClient.CreateAIAgentAsync()` from [Microsoft.Agents.AI.AzureAI](https://www.nuget.org/packages/Microsoft.Agents.AI.AzureAI/) |
| [`FoundrySingleAgent`](./FoundrySingleAgent/) | Single agent with local C# tool execution (hotel search) using `AIProjectClient.CreateAIAgentAsync()` from [Microsoft.Agents.AI.AzureAI](https://www.nuget.org/packages/Microsoft.Agents.AI.AzureAI/) |

## Common Prerequisites

Before running any sample, ensure you have:

1. **.NET 10 SDK** or later — [Download](https://dotnet.microsoft.com/download/dotnet/10.0)
2. **Azure CLI** installed — [Install guide](https://learn.microsoft.com/cli/azure/install-azure-cli)
3. **Azure OpenAI** or **Microsoft Foundry project** with a chat model deployed (e.g., `gpt-4o-mini`)

### Authenticate with Azure CLI

All samples use `DefaultAzureCredential` for authentication, which automatically probes multiple credential sources (environment variables, managed identity, Azure CLI, etc.). For local development, the simplest approach is to authenticate via Azure CLI:

```powershell
az login
az account show  # Verify the correct subscription
```

### Common Environment Variables

Most samples require one or more of these environment variables:

| Variable | Used By | Description |
|----------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Most samples | Your Azure OpenAI resource endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Most samples | Chat model deployment name (defaults to `gpt-4o-mini`) |
| `AZURE_AI_PROJECT_ENDPOINT` | AgentWithLocalTools, FoundryMultiAgent, FoundrySingleAgent | Microsoft Foundry project endpoint |
| `MODEL_DEPLOYMENT_NAME` | AgentWithLocalTools, FoundryMultiAgent, FoundrySingleAgent | Chat model deployment name (defaults to `gpt-4o-mini`) |

See each sample's README for the specific variables required.

## Microsoft Foundry Setup (for samples that use Foundry)

Some samples (`AgentWithLocalTools`, `FoundrySingleAgent`, `FoundryMultiAgent`) connect to a Microsoft Foundry project. If you're using these samples, you'll need additional setup.

### Azure AI Developer Role

Some Foundry operations require the **Azure AI Developer** role on the Cognitive Services resource. Even if you created the project, you may not have this role by default.

```powershell
az role assignment create `
  --role "Azure AI Developer" `
  --assignee "your-email@microsoft.com" `
  --scope "/subscriptions/{subscription-id}/resourceGroups/{resource-group}/providers/Microsoft.CognitiveServices/accounts/{account-name}"
```

> **Note**: You need **Owner** or **User Access Administrator** permissions on the resource to assign roles. If you don't have this, you may need to request JIT (Just-In-Time) elevated access via [Azure PIM](https://portal.azure.com/#view/Microsoft_Azure_PIMCommon/ActivationMenuBlade/~/aadmigratedresource).

For more details on permissions, see [Microsoft Foundry Permissions](https://aka.ms/FoundryPermissions).

## Running a Sample

Each sample runs as a standalone hosted agent on `http://localhost:8088/`:

```powershell
cd <sample-directory>
dotnet run
```

### Interacting with the Agent

Each sample includes a `run-requests.http` file for testing with the [VS Code REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) extension, or you can use PowerShell:

```powershell
$body = @{ input = "Your question here" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8088/responses" -Method Post -Body $body -ContentType "application/json"
```

## Deploying to Microsoft Foundry

Each sample includes a `Dockerfile` and `agent.yaml` for deployment. To deploy your agent to Microsoft Foundry, follow the [hosted agents deployment guide](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents).

## Troubleshooting

### `PermissionDenied` — lacks `agents/write` data action

Assign the **Azure AI Developer** role to your user. See [Azure AI Developer Role](#azure-ai-developer-role) above.

### Multi-framework error when running `dotnet run`

If you see "Your project targets multiple frameworks", specify the framework:

```powershell
dotnet run --framework net10.0
```
