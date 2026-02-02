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

## Configuration

Update your `local.settings.json` with your Azure OpenAI credentials:

```json
{
  "Values": {
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
    "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME": "your-deployment-name",
    "AZURE_OPENAI_KEY": "your-api-key-if-not-using-rbac"
  }
}
```

## Running the Sample

1. **Start the Function App**:
   ```bash
   cd python/samples/getting_started/azure_functions/08_mcp_server
   func start
   ```

2. **Note the MCP Server Endpoint**: When the app starts, you'll see the MCP server endpoint in the terminal output. It will look like:
   ```
   MCP server endpoint:  http://localhost:7071/runtime/webhooks/mcp
   ```

## Testing MCP Tool Integration

### Using MCP Inspector

1. Install the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector)
2. Connect using the MCP server endpoint from your terminal output
3. Select **"Streamable HTTP"** as the transport method
4. Test the available MCP tools:
   - `StockAdvisor` - Available only as MCP tool
   - `PlantAdvisor` - Available as both HTTP and MCP tool

### Using Other MCP Clients

Any MCP-compatible client can connect to the server endpoint and utilize the exposed agent tools. The agents will appear as callable tools within the MCP protocol.

## Testing HTTP Endpoints

For agents with HTTP triggers enabled (Joker and PlantAdvisor), you can test them using curl:

```bash
# Test Joker agent (HTTP only)
curl -X POST http://localhost:7071/api/agents/Joker/run \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me a joke"}'

# Test PlantAdvisor agent (HTTP and MCP)
curl -X POST http://localhost:7071/api/agents/PlantAdvisor/run \
  -H "Content-Type: application/json" \
  -d '{"message": "Recommend an indoor plant"}'
```

Note: StockAdvisor does not have HTTP endpoints and is only accessible via MCP tool triggers.

## Expected Output

**HTTP Responses** will be returned directly to your HTTP client.

**MCP Tool Responses** will be visible in:
- The terminal where `func start` is running
- Your MCP client interface
- The DTS dashboard at `http://localhost:8080` (if using Durable Task Scheduler)

## Health Check

Check the health endpoint to see which agents have which triggers enabled:

```bash
curl http://localhost:7071/api/health
```

Expected response:

```json
{
  "status": "healthy",
  "agents": [
    {
      "name": "Joker",
      "type": "Agent",
      "http_endpoint_enabled": true,
      "mcp_tool_enabled": false
    },
    {
      "name": "StockAdvisor",
      "type": "Agent",
      "http_endpoint_enabled": false,
      "mcp_tool_enabled": true
    },
    {
      "name": "PlantAdvisor",
      "type": "Agent",
      "http_endpoint_enabled": true,
      "mcp_tool_enabled": true
    }
  ],
  "agent_count": 3
}
```

## Code Structure

The sample shows how to enable MCP tool triggers with flexible agent configuration:

```python
from agent_framework.azure import AgentFunctionApp, AzureOpenAIChatClient

# Create Azure OpenAI Chat Client
chat_client = AzureOpenAIChatClient()

# Define agents with different roles
joker_agent = chat_client.as_agent(
    name="Joker",
    instructions="You are good at telling jokes.",
)

stock_agent = chat_client.as_agent(
    name="StockAdvisor",
    instructions="Check stock prices.",
)

plant_agent = chat_client.as_agent(
    name="PlantAdvisor",
    instructions="Recommend plants.",
    description="Get plant recommendations.",
)

# Create the AgentFunctionApp
app = AgentFunctionApp(enable_health_check=True)

# Configure agents with different trigger combinations:
# HTTP trigger only (default)
app.add_agent(joker_agent)

# MCP tool trigger only (HTTP disabled)
app.add_agent(stock_agent, enable_http_endpoint=False, enable_mcp_tool_trigger=True)

# Both HTTP and MCP tool triggers enabled
app.add_agent(plant_agent, enable_http_endpoint=True, enable_mcp_tool_trigger=True)
```

This automatically creates the following endpoints based on agent configuration:
- `POST /api/agents/{AgentName}/run` - HTTP endpoint (when `enable_http_endpoint=True`)
- MCP tool triggers for agents with `enable_mcp_tool_trigger=True`
- `GET /api/health` - Health check endpoint showing agent configurations

## Learn More

- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
- [Microsoft Agent Framework Documentation](https://github.com/microsoft/agent-framework)
- [Azure Functions Documentation](https://learn.microsoft.com/azure/azure-functions/)
