"""Expose Azure OpenAI agents as MCP (Model Context Protocol) tools.

Components used in this sample:
- AzureOpenAIChatClient to create an agent with the Azure OpenAI deployment.
- AgentFunctionApp to expose standard HTTP endpoints via Durable Functions.
- MCPServerExtension to automatically generate MCP-compliant endpoints for agent tools.

Prerequisites: set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, plus either
`AZURE_OPENAI_API_KEY` or authenticate with Azure CLI before starting the Functions host."""

import logging
from typing import Any

from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.azurefunctions import AgentFunctionApp
from agent_framework.azurefunctions.mcp import MCPServerExtension

logger = logging.getLogger(__name__)


def get_weather(location: str) -> dict[str, Any]:
    """Get current weather for a location."""

    logger.info(f"🔧 [TOOL CALLED] get_weather(location={location})")
    result = {
        "location": location,
        "temperature": 72,
        "conditions": "Sunny",
        "humidity": 45,
        "wind_speed": 5,
    }
    logger.info(f"✓ [TOOL RESULT] {result}")
    return result


# 1. Create the weather agent with a tool function.
def _create_weather_agent() -> Any:
    """Create the WeatherAgent with get_weather tool."""

    return AzureOpenAIChatClient().create_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather assistant. Use the get_weather tool to provide weather information.",
        tools=[get_weather],
    )


# 2. Register the agent with AgentFunctionApp to expose standard HTTP endpoints.
app = AgentFunctionApp(agents=[_create_weather_agent()], enable_health_check=True)

# 3. Enable MCP protocol support with 2 additional lines.
mcp = MCPServerExtension(app)
app.register_mcp_server(mcp)

"""
Expected output when invoking `POST /api/agents/WeatherAgent/run`:

HTTP/1.1 202 Accepted
{
  "status": "accepted",
  "response": "Agent request accepted",
  "message": "What is the weather in Seattle?",
  "conversation_id": "<guid>",
  "correlation_id": "<guid>"
}

Expected output when invoking `GET /api/mcp/v1/tools`:

HTTP/1.1 200 OK
{
  "tools": [
    {
      "name": "WeatherAgent",
      "description": "You are a helpful weather assistant...",
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
"""
