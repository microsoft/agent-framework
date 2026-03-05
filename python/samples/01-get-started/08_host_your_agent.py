# Copyright (c) Microsoft. All rights reserved.

# ruff: noqa: E305
# fmt: off
from typing import Any

from agent_framework.azure import AgentFunctionApp, AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""Host your agent with Azure Functions.

This sample shows the Python hosting pattern used in docs:
- Create an agent with `AzureOpenAIChatClient`
- Register it with `AgentFunctionApp`
- Run with Azure Functions Core Tools (`func start`)

Prerequisites:
  pip install agent-framework-azurefunctions --pre

Environment variables:
  AZURE_OPENAI_ENDPOINT
  AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
"""


# <create_agent>
def _create_agent() -> Any:
    """Create a hosted agent backed by Azure OpenAI."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name="HostedAgent",
        instructions="You are a helpful assistant hosted in Azure Functions.",
    )


# </create_agent>

# <host_agent>
app = AgentFunctionApp(agents=[_create_agent()], enable_health_check=True, max_poll_retries=50)
# </host_agent>


if __name__ == "__main__":
    print("Start the Functions host with: func start")
    print("Then call: POST /api/agents/HostedAgent/run")
