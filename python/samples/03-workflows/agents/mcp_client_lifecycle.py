# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from agent_framework_orchestrations import SequentialBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from mcp import Client

load_dotenv()

"""
Sample: Use a caller-owned MCP Client for the complete lifetime of a workflow run.

The researcher uses the public Microsoft Learn MCP server, then the technical writer
turns the research into a concise answer. The caller creates and enters the high-level
MCP Client, passes it to `MCPStreamableHTTPTool`, and keeps it open until the sequential
workflow finishes.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be set to the Microsoft Foundry project endpoint.
- FOUNDRY_MODEL must be set to a model deployment available in that project.
- Authentication uses AzureCliCredential; run `az login` before executing the sample.
"""


async def main() -> None:
    # 1) Create the shared chat client used by both workflow agents.
    chat_client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    MS_LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"

    # 2) Enter the caller-owned MCP Client before creating the MCP tool.
    async with Client(server=MS_LEARN_MCP_URL) as mcp_client:
        research_agent = Agent(
            client=chat_client,
            name="research_agent",
            tools=MCPStreamableHTTPTool(name="ms_learn", mcp_client=mcp_client),
            instructions="You are a Microsoft research agent backing your research with Microsoft Learn docs.",
        )
        writer_agent = Agent(
            client=chat_client,
            name="writer_agent",
            instructions=(
                "You are a technical writer who explains concepts clearly, concisely, and focuses on the key points."
            ),
        )

        # 3) Build and run the workflow while the caller-owned MCP Client remains entered.
        workflow = SequentialBuilder(participants=[research_agent, writer_agent]).build().as_agent()
        response = await workflow.run("Explain how to set up the Python Agent Framework.")
        print(response.text)

        """
        Sample output:

        A Microsoft Learn-grounded explanation of how to install Agent Framework,
        configure a model provider, authenticate, create an agent, and run it.

        The exact response varies by model. The workflow-as-agent response contains
        the final technical writer output.
        """


if __name__ == "__main__":
    asyncio.run(main())
