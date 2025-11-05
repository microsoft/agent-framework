"""Azure Functions single-agent sample showcasing how to host a single Azure OpenAI agent.

The sample reads the required endpoint and deployment environment variables, configures the Azure OpenAI chat client (using either an API key or Azure CLI credentials), and registers a joke-telling agent with an Azure Functions app that can optionally expose a health check.

Summary: Demonstrates configuring and deploying a single 'Joker' agent via Azure Functions."""

import logging
import os
from typing import Any

from azure.identity import AzureCliCredential
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.azurefunctions import AgentFunctionApp


logger = logging.getLogger(__name__)


AZURE_OPENAI_ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_DEPLOYMENT_ENV = "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
AZURE_OPENAI_API_KEY_ENV = "AZURE_OPENAI_API_KEY"


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


def _create_agent() -> Any:
    """Create the Joker agent."""

    client_kwargs = _build_client_kwargs()
    return AzureOpenAIChatClient(**client_kwargs).create_agent(
        name="Joker",
        instructions="You are good at telling jokes.",
    )


app = AgentFunctionApp(agents=[_create_agent()], enable_health_check=True)
