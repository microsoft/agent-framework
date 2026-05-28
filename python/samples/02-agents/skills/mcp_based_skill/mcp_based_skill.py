# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

# Uncomment this filter to suppress the experimental Skills warning before
# using the sample's Skills APIs.
# import warnings
# warnings.filterwarnings("ignore", message=r"\[SKILLS\].*", category=FutureWarning)
from agent_framework import Agent, McpSkillsSource, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

"""
MCP-Based Agent Skills

This sample demonstrates how to discover Agent Skills served over the
Model Context Protocol (MCP) using :class:`McpSkillsSource`.

The sample connects to a remote MCP server that exposes skill resources
following the SEP-2640 convention:

* ``skill://index.json`` — discovery document listing all skills
* ``skill://<skill-name>/SKILL.md`` — the skill instructions

To run, set ``MCP_SKILLS_SERVER_URL`` to the streamable HTTP endpoint of an
MCP server that hosts SEP-2640 skill resources. To create such a server,
see ``samples/02-agents/mcp/agent_as_mcp_server.py`` for an example of
hosting MCP via the Agent Framework, or the experimental MCP skills
reference servers at:

    https://github.com/modelcontextprotocol/experimental-ext-skills
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
        #    McpSkillsSource reads skill://index.json and creates one
        #    McpSkill per skill-md entry; SKILL.md bodies are fetched
        #    on demand via resources/read.
        skills_provider = SkillsProvider(McpSkillsSource(client=session))

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
        ) as agent:
            response = await agent.run(
                "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?"
            )
            print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:

Discovering MCP-based skills
------------------------------------------------------------
Agent: Here are your conversions:

1. **26.2 miles -> 42.16 km** (a marathon distance)
2. **75 kg -> 165.35 lbs**

Conversion factors used: miles * 1.60934 and kilograms * 2.20462.
"""
