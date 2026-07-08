# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

# Uncomment this filter to suppress the experimental Skills warning before
# using the sample's Skills APIs.
# import warnings
# warnings.filterwarnings("ignore", message=r"\[SKILLS\].*", category=FutureWarning)
from agent_framework import Agent, MCPSkillsSource, SkillsProvider, ToolApprovalMiddleware
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

"""
MCP-Based Agent Skills

This sample demonstrates how to discover Agent Skills served over the
Model Context Protocol (MCP) using :class:`MCPSkillsSource`.

The sample connects to a remote MCP server that exposes skill resources
under the ``skill://`` URI scheme:

* ``skill://index.json`` — discovery document listing all skills
* ``skill://<skill-name>/SKILL.md`` — the skill instructions

To run, set ``MCP_SKILLS_SERVER_URL`` to the streamable HTTP endpoint of an
MCP server that hosts the skill resources.
"""


async def main() -> None:
    """Connect to a remote MCP skills server and run the agent."""
    load_dotenv()

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")
    mcp_url = os.environ["MCP_SKILLS_SERVER_URL"]

    print("Discovering MCP-based skills")
    print("-" * 60)

    # 1. Connect to the MCP server over streamable HTTP.
    async with streamable_http_client(url=mcp_url) as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()

        # 2. Build a SkillsProvider that discovers skills over MCP.
        #    MCPSkillsSource reads skill://index.json and creates one
        #    MCPSkill per skill-md entry; SKILL.md bodies are fetched
        #    on demand via resources/read.
        skills_provider = SkillsProvider(MCPSkillsSource(client=session))

        # 3. Run the agent.
        client = FoundryChatClient(
            project_endpoint=endpoint,
            model=deployment,
            credential=AzureCliCredential(),
        )

        async with Agent(
            client=client,
            instructions="You are a helpful assistant. Use available skills to answer the user.",
            context_providers=[skills_provider],
            middleware=[ToolApprovalMiddleware(auto_approval_rules=[SkillsProvider.all_tools_auto_approval_rule])],
        ) as agent:
            query = input("User: ").strip()  # noqa: ASYNC250
            if not query:
                return
            session = agent.create_session()
            response = await agent.run(query, session=session)
            print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
