"""Host multiple Azure OpenAI agents inside a single Azure Functions app.

Components used in this sample:
- AzureOpenAIChatClient to create agents bound to a shared Azure OpenAI deployment.
- AgentFunctionApp to register multiple agents and expose dedicated HTTP endpoints.
- Custom tool functions to demonstrate tool invocation from different agents.

Prerequisites: set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, plus either
`AZURE_OPENAI_API_KEY` or authenticate with Azure CLI before starting the Functions host."""

import logging
from typing import Any

from agent_framework.azure import AgentFunctionApp, AzureOpenAIChatClient
from azure.identity import AzureCliCredential

logger = logging.getLogger(__name__)


def get_weather(location: str) -> dict[str, Any]:
    """Get current weather for a location."""

    logger.info(f"🔧 [TOOL CALLED] get_weather(location={location})")
    result = {
        "location": location,
        "temperature": 72,
        "conditions": "Sunny",
        "humidity": 45,
    }
    logger.info(f"✓ [TOOL RESULT] {result}")
    return result


def calculate_tip(bill_amount: float, tip_percentage: float = 15.0) -> dict[str, Any]:
    """Calculate tip amount and total bill."""

    logger.info(
        f"🔧 [TOOL CALLED] calculate_tip(bill_amount={bill_amount}, tip_percentage={tip_percentage})"
    )
    tip = bill_amount * (tip_percentage / 100)
    total = bill_amount + tip
    result = {
        "bill_amount": bill_amount,
        "tip_percentage": tip_percentage,
        "tip_amount": round(tip, 2),
        "total": round(total, 2),
    }
    logger.info(f"✓ [TOOL RESULT] {result}")
    return result


# 1. Create multiple agents, each with its own instruction set and tools.
chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

weather_agent = chat_client.create_agent(
    name="WeatherAgent",
    instructions="You are a helpful weather assistant. Provide current weather information.",
    tools=[get_weather],
)

math_agent = chat_client.create_agent(
    name="MathAgent",
    instructions="You are a helpful math assistant. Help users with calculations like tip calculations.",
    tools=[calculate_tip],
)


# 2. Register both agents with AgentFunctionApp to expose their HTTP routes and health check.
app = AgentFunctionApp(agents=[weather_agent, math_agent], enable_health_check=True, max_poll_retries=50)

# Option 2: Add agents after initialization (commented out as we're using Option 1)
# app = AgentFunctionApp(enable_health_check=True)
# app.add_agent(weather_agent)
# app.add_agent(math_agent)

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

Expected output when invoking `POST /api/agents/MathAgent/run`:

HTTP/1.1 202 Accepted
{
  "status": "accepted",
  "response": "Agent request accepted",
  "message": "Calculate a 20% tip on a $50 bill",
  "conversation_id": "<guid>",
  "correlation_id": "<guid>"
}
"""
