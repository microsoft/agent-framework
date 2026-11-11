# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent, SkillsProvider, ToolApprovalMiddleware
from agent_framework.foundry import FoundryChatClient, FoundryToolbox
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Foundry Chat Client with Toolbox-Hosted Skills

Discover Agent Skills served by a Microsoft Foundry Toolbox MCP endpoint and
inject them into a ``FoundryChatClient`` agent. ``FoundryToolbox`` owns the MCP
connection and authentication, while its skills provider resolves
identity-scoped resources through the current connection.

Prerequisites:
- A Microsoft Foundry project with a toolbox that exposes
  ``skill://index.json`` with ``skill-md`` entries
- FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL environment variables set
- FOUNDRY_TOOLBOX_MCP_SERVER_URL: the toolbox's MCP endpoint URL, e.g.
  ``https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/<name>/mcp?api-version=v1``
- Azure CLI authentication (``az login``)
"""


async def main() -> None:
    """Example showing toolbox-hosted MCP skills for a Foundry Chat Client agent."""
    credential = AzureCliCredential()
    toolbox = FoundryToolbox(
        credential,
        url=os.environ["FOUNDRY_TOOLBOX_MCP_SERVER_URL"],
        load_tools=False,
    )
    skills_provider = toolbox.as_skills_provider()

    async with Agent(
        client=FoundryChatClient(credential=credential),
        name="ToolboxMCPSkillsAgent",
        instructions="You are a helpful assistant. Use available skills to answer the user.",
        tools=[toolbox],
        context_providers=[skills_provider],
        middleware=[ToolApprovalMiddleware(auto_approval_rules=[SkillsProvider.all_tools_auto_approval_rule])],
    ) as agent:
        query = input("User: ").strip()  # noqa: ASYNC250
        if not query:
            return
        session = agent.create_session()
        response = await agent.run(query, session=session)
        print(f"Assistant: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
