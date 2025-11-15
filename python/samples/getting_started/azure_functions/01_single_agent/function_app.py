"""Host a single Azure OpenAI-powered agent inside Azure Functions.

Components used in this sample:
- AzureOpenAIChatClient to call the Azure OpenAI chat deployment.
- AgentFunctionApp to expose HTTP endpoints via the Durable Functions extension.

Prerequisites: set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` (plus `AZURE_OPENAI_API_KEY` or Azure CLI authentication) before starting the Functions host."""

from typing import Any

from agent_framework.azure import AgentFunctionApp, AzureOpenAIChatClient
from azure.identity import AzureCliCredential
# 1. Instantiate the agent with the chosen deployment and instructions.
def _create_agent() -> Any:
    """Create the Joker agent."""

    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        name="Joker",
        instructions="You are good at telling jokes.",
    )


# 2. Register the agent with AgentFunctionApp so Azure Functions exposes the required triggers.
app = AgentFunctionApp(agents=[_create_agent()], enable_health_check=True, max_poll_retries=50)

"""
Expected output when invoking `POST /api/agents/Joker/run` with plain-text input:

HTTP/1.1 202 Accepted
{
  "status": "accepted",
  "response": "Agent request accepted",
  "message": "Tell me a short joke about cloud computing.",
  "conversation_id": "<guid>",
  "correlation_id": "<guid>"
}
"""
