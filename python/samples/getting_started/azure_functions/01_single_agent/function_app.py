"""Host a single Azure OpenAI-powered agent inside Azure Functions.

Components used in this sample:
- AzureOpenAIChatClient to call the Azure OpenAI chat deployment.
- AgentFunctionApp to expose HTTP endpoints via the Durable Functions extension.

Prerequisites: set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` (plus `AZURE_OPENAI_API_KEY` or Azure CLI authentication) before starting the Functions host."""

import logging
import os
from typing import Any

from azure.identity import AzureCliCredential
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.azurefunctions import AgentFunctionApp


logger = logging.getLogger(__name__)


# 1. Define the environment variable keys required to configure Azure OpenAI.
AZURE_OPENAI_ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_DEPLOYMENT_ENV = "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
AZURE_OPENAI_API_KEY_ENV = "AZURE_OPENAI_API_KEY"


# 2. Build the Azure OpenAI chat client configuration used by the agent.
def _build_client_kwargs() -> dict[str, Any]:
    """Construct Azure OpenAI client options."""

    endpoint = os.getenv(AZURE_OPENAI_ENDPOINT_ENV)
    if not endpoint:
        raise RuntimeError(f"{AZURE_OPENAI_ENDPOINT_ENV} environment variable is required.")

    deployment = os.getenv(AZURE_OPENAI_DEPLOYMENT_ENV)
    if not deployment:
        raise RuntimeError(f"{AZURE_OPENAI_DEPLOYMENT_ENV} environment variable is required.")

    logger.info("[SingleAgent] Using deployment '%s' at '%s'", deployment, endpoint)

    client_kwargs: dict[str, Any] = {
        "endpoint": endpoint,
        "deployment_name": deployment,
    }

    api_key = os.getenv(AZURE_OPENAI_API_KEY_ENV)
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        client_kwargs["credential"] = AzureCliCredential()

    return client_kwargs


# 3. Instantiate the agent with the chosen deployment and instructions.
def _create_agent() -> Any:
    """Create the Joker agent."""

    client_kwargs = _build_client_kwargs()
    return AzureOpenAIChatClient(**client_kwargs).create_agent(
        name="Joker",
        instructions="You are good at telling jokes.",
    )


# 4. Register the agent with AgentFunctionApp so Azure Functions exposes the required triggers.
app = AgentFunctionApp(agents=[_create_agent()], enable_health_check=True)

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
