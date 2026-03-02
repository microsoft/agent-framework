# Hosted Agent Samples

These samples demonstrate how to build and host AI agents using the [Azure AI AgentServer SDK](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.agentserver.agentframework-readme). Each sample can be run locally and deployed to Microsoft Foundry as a hosted agent.

## Samples

| Sample | Description |
|--------|-------------|
| [`AgentWithTools`](./AgentWithTools/) | Foundry tools (MCP + code interpreter) via `UseFoundryTools` |
| [`AgentWithLocalTools`](./AgentWithLocalTools/) | Local C# function tool execution (Seattle hotel search) |
| [`AgentThreadAndHITL`](./AgentThreadAndHITL/) | Human-in-the-loop with `ApprovalRequiredAIFunction` and thread persistence |
| [`AgentWithHostedMCP`](./AgentWithHostedMCP/) | Hosted MCP server tool (Microsoft Learn search) |
| [`AgentWithTextSearchRag`](./AgentWithTextSearchRag/) | RAG with `TextSearchProvider` (Contoso Outdoors) |
| [`AgentsInWorkflows`](./AgentsInWorkflows/) | Sequential workflow pipeline (translation chain) |

## Common Prerequisites

Before running any sample, ensure you have:

1. **.NET 10 SDK** or later — [Download](https://dotnet.microsoft.com/download/dotnet/10.0)
2. **Azure CLI** installed — [Install guide](https://learn.microsoft.com/cli/azure/install-azure-cli)
3. **Azure OpenAI** or **Azure AI Foundry project** with a chat model deployed (e.g., `gpt-4o-mini`)

### Authenticate with Azure CLI

All samples use `AzureCliCredential` for authentication. Make sure you're logged in:

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
| `AZURE_AI_PROJECT_ENDPOINT` | AgentWithTools, AgentWithLocalTools | Azure AI Foundry project endpoint |
| `MCP_TOOL_CONNECTION_ID` | AgentWithTools | Foundry MCP tool connection name |
| `MODEL_DEPLOYMENT_NAME` | AgentWithLocalTools | Chat model deployment name (defaults to `gpt-4o-mini`) |

See each sample's README for the specific variables required.

## Azure AI Foundry Setup (for samples that use Foundry)

Some samples (`AgentWithTools`, `AgentWithLocalTools`) connect to an Azure AI Foundry project. If you're using these samples, you'll need additional setup.

### Azure AI Developer Role

The `UseFoundryTools` extension requires the **Azure AI Developer** role on the Cognitive Services resource. Even if you created the project, you may not have this role by default.

```powershell
az role assignment create `
  --role "Azure AI Developer" `
  --assignee "your-email@microsoft.com" `
  --scope "/subscriptions/{subscription-id}/resourceGroups/{resource-group}/providers/Microsoft.CognitiveServices/accounts/{account-name}"
```

> **Note**: You need **Owner** or **User Access Administrator** permissions on the resource to assign roles. If you don't have this, you may need to request JIT (Just-In-Time) elevated access via [Azure PIM](https://portal.azure.com/#view/Microsoft_Azure_PIMCommon/ActivationMenuBlade/~/aadmigratedresource).

For more details on permissions, see [Azure AI Foundry Permissions](https://aka.ms/FoundryPermissions).

### Creating an MCP Tool Connection

The `AgentWithTools` sample requires an MCP tool connection configured in your Foundry project:

1. Go to the [Azure AI Foundry portal](https://ai.azure.com)
2. Navigate to your project
3. Go to **Connected resources** → **+ New connection** → **Model Context Protocol tool**
4. Fill in:
   - **Name**: `SampleMCPTool` (or any name you prefer)
   - **Remote MCP Server endpoint**: `https://learn.microsoft.com/api/mcp`
   - **Authentication**: `Unauthenticated`
5. Click **Connect**

The connection **name** (e.g., `SampleMCPTool`) is used as the `MCP_TOOL_CONNECTION_ID` environment variable.

> **Important**: Use only the connection **name**, not the full ARM resource ID.

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

### `Project connection ... was not found`

Make sure `MCP_TOOL_CONNECTION_ID` contains only the connection **name** (e.g., `SampleMCPTool`), not the full ARM resource ID path.

### `AZURE_AI_PROJECT_ENDPOINT must be set`

The `UseFoundryTools` extension requires `AZURE_AI_PROJECT_ENDPOINT`. Set it to your Foundry project endpoint (e.g., `https://your-resource.services.ai.azure.com/api/projects/your-project`).

### Multi-framework error when running `dotnet run`

If you see "Your project targets multiple frameworks", specify the framework:

```powershell
dotnet run --framework net10.0
```
