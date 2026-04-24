# Copyright (c) Microsoft. All rights reserved.

# ruff: noqa: E305
# fmt: off
from typing import Any

from agent_framework import Agent
from agent_framework.azure import AgentFunctionApp
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

"""Host your agent with Azure Functions.
This sample shows the Python hosting pattern used in docs:
- Create an agent with `FoundryChatClient`
- Register it with `AgentFunctionApp`
- Run with Azure Functions Core Tools (`func start`)
Prerequisites:
  pip install agent-framework-azurefunctions --pre
"""


# <create_agent>
def _create_agent() -> Any:
    """Create a hosted agent backed by Azure OpenAI."""
    return Agent(
        client=FoundryChatClient(
            project_endpoint="https://your-project.services.ai.azure.com",
            model="gpt-4o",
            credential=AzureCliCredential(),
        ),
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
