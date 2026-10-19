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


async def main() -> None:
    chat_client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    MS_LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"

    async with Client(server=MS_LEARN_MCP_URL) as mcp_client:
        research_agent = Agent(
            client=chat_client,
            name="research_agent",
            tools=MCPStreamableHTTPTool(name="ms_learn", mcp_client=mcp_client),
            instructions="You are a Microsoft research agent backing your research with the MS learn docs"
        )
        writer_agent = Agent(
            client=chat_client,
            name="writer_agent",
            instructions="You are a technical writer that explains concepts clearly, concisely and focuses on the key points."
        )
        workflow = SequentialBuilder(participants=[research_agent, writer_agent]).build().as_agent()
        response = await workflow.run("Explain to me how to setup the python Agent Framework")
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
