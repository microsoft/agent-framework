# Agent as MCP Tool Sample

This sample demonstrates how to configure AI agents to be accessible as both HTTP endpoints and [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools, enabling flexible integration patterns for AI agent consumption.

## Key Concepts Demonstrated

- **Multi-trigger Agent Configuration**: Configure agents to support HTTP triggers, MCP tool triggers, or both
- **Microsoft Agent Framework Integration**: Use the framework to define AI agents with specific roles and capabilities
- **Flexible Agent Registration**: Register agents with customizable trigger configurations
- **MCP Server Hosting**: Expose agents as MCP tools for consumption by MCP-compatible clients

## Sample Architecture

This sample creates three agents with different trigger configurations:

| Agent | Role | HTTP Trigger | MCP Tool Trigger | Description |
|-------|------|--------------|------------------|-------------|
| **Joker** | Comedy specialist | ✅ Enabled | ❌ Disabled | Accessible only via HTTP requests |
| **StockAdvisor** | Financial data | ❌ Disabled | ✅ Enabled | Accessible only as MCP tool |
| **PlantAdvisor** | Indoor plant recommendations | ✅ Enabled | ✅ Enabled | Accessible via both HTTP and MCP |

## Environment Setup

See the [README.md](../README.md) file in the parent directory for complete setup instructions, including:

- Prerequisites installation
- Azure OpenAI configuration
- Durable Task Scheduler setup
- Storage emulator configuration

For this sample, you'll also need to install [node.js](https://nodejs.org/en/download) in order to use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) tool.

## Configuration

Update your `local.settings.json` with your Azure OpenAI credentials:

```json
{
  "Values": {
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
    "AZURE_OPENAI_DEPLOYMENT": "your-deployment-name",
    "AZURE_OPENAI_KEY": "your-api-key-if-not-using-rbac"
  }
}
```

## Running the Sample

1. **Start the Function App**:

   ```bash
   cd dotnet/samples/AzureFunctions/07_AgentAsMcpTool
   func start
   ```

2. **Note the MCP Server Endpoint**: When the app starts, you'll see the MCP server endpoint in the terminal output. It will look like:

   ```text
   MCP server endpoint:  http://localhost:7071/runtime/webhooks/mcp
   ```

## Testing MCP Tool Integration

Any MCP-compatible client can connect to the server endpoint and utilize the exposed agent tools. The agents will appear as callable tools within the MCP protocol.

### Using MCP Inspector

1. Run the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) from the command line:

   ```bash
   npx @modelcontextprotocol/inspector
   ```

1. Connect using the MCP server endpoint from your terminal output

   - For **Transport Type**, select **"Streamable HTTP"**
   - For **URL**, enter the MCP server endpoint `http://localhost:7071/runtime/webhooks/mcp`
   - Click the **Connect** button

1. Click the **List Tools** button to see the available MCP tools. You should see the `StockAdvisor` and `PlantAdvisor` tools.

1. Test the available MCP tools:

   - **StockAdvisor** - Set "MSFT ATH" (ATH is "all time high") as the query and click the **Run Tool** button.
   - **PlantAdvisor** - Set "Low light in Seattle" as the query and click the **Run Tool** button.

You'll see the results of the tool calls in the MCP Inspector interface under the **Tool Results** section. You should also see the results in the terminal where you ran the `func start` command.
