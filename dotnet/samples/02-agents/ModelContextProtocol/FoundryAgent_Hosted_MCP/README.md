# Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Microsoft Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Microsoft Foundry resource endpoint
$env:FOUNDRY_MODEL="gpt-5.4-mini"  # Optional, defaults to gpt-5.4-mini
```

## Authenticating a hosted MCP server with a Foundry project connection

A hosted MCP server can authenticate through a Foundry **project connection** instead of an inline
authorization token or headers. The connection stores the credentials and the platform injects them
at request time. This mirrors the Python `FoundryChatClient.get_mcp_tool(..., project_connection_id=...)`.

Use the `FoundryAITool.CreateMcpTool` overload that takes a `projectConnectionId`:

```csharp
using Microsoft.Agents.AI.Foundry;
using OpenAI.Responses;

AITool tool = FoundryAITool.CreateMcpTool(
    serverLabel: "github",
    serverUri: new Uri("https://api.githubcopilot.com/mcp"),
    projectConnectionId: "my-foundry-connection",
    toolCallApprovalPolicy: new McpToolCallApprovalPolicy(GlobalMcpToolCallApprovalPolicy.AlwaysRequireApproval));
```

The resulting tool sends `project_connection_id` on the MCP tool to Foundry.
