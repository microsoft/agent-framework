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
      "httpEndpointEnabled": true,
      "mcpToolTriggerEnabled": false
    },
    {
      "name": "StockAdvisor",
      "type": "Agent",
      "httpEndpointEnabled": false,
      "mcpToolTriggerEnabled": true
    },
    {
      "name": "PlantAdvisor",
      "type": "Agent",
      "httpEndpointEnabled": true,
      "mcpToolTriggerEnabled": true
    }
  ],
  "agent_count": 3
}
```

## Learn More

- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
- [Microsoft Agent Framework Documentation](https://github.com/Azure/agent-framework)
- [Azure Functions Documentation](https://learn.microsoft.com/azure/azure-functions/) Sample (Python)

This sample demonstrates how to expose AI agents as MCP (Model Context Protocol) tools using the Durable Extension for Agent Framework. The sample creates a weather agent and exposes it via both standard HTTP endpoints and MCP protocol endpoints for use with MCP-compatible clients like Claude Desktop, Cursor, or VSCode.

## Key Concepts Demonstrated

- Defining an AI agent with the Microsoft Agent Framework and exposing it through MCP protocol.
- Using `MCPServerExtension` to automatically generate MCP-compliant endpoints.
- Supporting both direct HTTP API access and MCP JSON-RPC protocol for the same agent.
- Session-based conversation management compatible with MCP clients.
- Dual-mode access: standard HTTP triggers (`/api/agents/{agent_name}/run`) and MCP endpoints (`/api/mcp/v1/*`).

## Environment Setup

### 1. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux/macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

### 3. Configure local settings

Copy `local.settings.json.template` to `local.settings.json`, then set the Azure OpenAI values (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and optionally `AZURE_OPENAI_API_KEY`) to match your environment.

## Running the Sample

With the environment setup and function app running, you can test the sample using either standard HTTP endpoints or MCP protocol endpoints.

You can use the `demo.http` file to send requests, or command line tools as shown below.

### Test via Standard HTTP Endpoint

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/agents/WeatherAgent/run \
    -H "Content-Type: application/json" \
    -d '{"message": "What is the weather in Seattle?"}'
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/agents/WeatherAgent/run `
    -ContentType application/json `
    -Body '{"message": "What is the weather in Seattle?"}'
```

Expected response:
```json
{
  "status": "accepted",
  "response": "Agent request accepted",
  "message": "What is the weather in Seattle?",
  "conversation_id": "<guid>",
  "correlation_id": "<guid>"
}
```

### Test MCP Endpoints

List available MCP tools:

Bash (Linux/macOS/WSL):

```bash
curl http://localhost:7071/api/mcp/v1/tools
```

PowerShell:

```powershell
Invoke-RestMethod -Uri http://localhost:7071/api/mcp/v1/tools
```

Call agent via MCP protocol:

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/mcp/v1/call \
    -H "Content-Type: application/json" \
    -d '{"name": "WeatherAgent", "arguments": {"message": "What is the weather in Seattle?"}}'
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/mcp/v1/call `
    -ContentType application/json `
    -Body '{"name": "WeatherAgent", "arguments": {"message": "What is the weather in Seattle?"}}'
```

## Using with MCP Clients

Once the function app is running, you can connect MCP-compatible clients to interact with your agents.

### Claude Desktop

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS or `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "weather-agent": {
      "url": "http://localhost:7071/api/mcp/v1"
    }
  }
}
```

### VSCode/Cursor

Configure your MCP client extension settings to connect to `http://localhost:7071/api/mcp/v1`.

## Code Structure

The sample shows how to enable MCP protocol support with minimal code changes:

```python
# Create your agent as usual
weather_agent = _create_weather_agent()

# Initialize the Function app
app = AgentFunctionApp(agents=[weather_agent])

# Enable MCP with just 2 lines
mcp = MCPServerExtension(app, [weather_agent])
app.register_mcp_server(mcp)
```

This automatically creates the following endpoints:
- `POST /api/agents/WeatherAgent/run` - Standard HTTP endpoint
- `POST /api/mcp/v1` - MCP JSON-RPC handler
- `GET /api/mcp/v1/tools` - List available MCP tools
- `POST /api/mcp/v1/call` - Direct MCP tool invocation

## Expected Output

When you call the agent via the standard HTTP endpoint, you receive a 202 Accepted response:

```json
{
  "status": "accepted",
  "response": "Agent request accepted",
  "message": "What is the weather in Seattle?",
  "conversation_id": "<guid>",
  "correlation_id": "<guid>"
}
```

When you list MCP tools, you receive the agent's metadata:

```json
{
  "tools": [
    {
      "name": "WeatherAgent",
      "description": "A helpful weather assistant",
      "inputSchema": {
        "type": "object",
        "properties": {
          "message": {"type": "string"},
          "sessionId": {"type": "string"}
        },
        "required": ["message"]
      }
    }
  ]
}
```
