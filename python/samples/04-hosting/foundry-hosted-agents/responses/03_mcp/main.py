# Copyright (c) Microsoft. All rights reserved.

import logging
import os

from agent_framework import Agent, ToolTypes
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


def main():
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    github_pat = os.environ["GITHUB_PAT"]
    tools: list[ToolTypes] = []
    if not github_pat:
        logger.warning("GITHUB_PAT environment variable is not set. The GitHub MCP tool will not get registered.")
    else:
        tools.append(
            client.get_mcp_tool(
                name="GitHub",
                url="https://api.githubcopilot.com/mcp/",
                headers={
                    "Authorization": f"Bearer {github_pat}",
                },
                approval_mode="never_require",
            )
        )

    agent = Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        tools=tools,
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
