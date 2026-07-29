# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from collections.abc import Generator

import httpx
from agent_framework import Agent, MCPSkillsSource, SkillsProvider, ToolApprovalMiddleware
from agent_framework.foundry import FoundryChatClient
from azure.core.credentials import TokenCredential
from azure.identity import AzureCliCredential, get_bearer_token_provider
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

# Load environment variables from .env file
load_dotenv()

"""
Foundry Chat Client with Toolbox-Hosted Skills

Discover Agent Skills served by a Microsoft Foundry Toolbox MCP endpoint
and inject them into a ``FoundryChatClient`` agent via ``MCPSkillsSource``.
The toolbox's discovery document (``skill://index.json``) is read once at
startup; SKILL.md bodies are fetched on demand as the agent uses them.

Prerequisites:
- A Microsoft Foundry project with a toolbox that exposes
  ``skill://index.json`` with ``skill-md`` entries
- FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL environment variables set
- FOUNDRY_TOOLBOX_MCP_SERVER_URL: the toolbox's MCP endpoint URL, e.g.
  ``https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/<name>/mcp?api-version=v1``
- Azure CLI authentication (``az login``)
"""


class _BearerAuth(httpx.Auth):
    """Attach a fresh Foundry bearer token to every request."""

    def __init__(self, credential: TokenCredential) -> None:
        self._get_token = get_bearer_token_provider(credential, "https://ai.azure.com/.default")

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


async def main() -> None:
    """Example showing toolbox-hosted MCP skills for a Foundry Chat Client agent."""
    credential = AzureCliCredential()

    # HTTP client that signs every request with a fresh Foundry bearer token
    # and advertises the toolbox preview feature flag, plus the MCP streamable
    # HTTP transport that uses it.
    async with (
        httpx.AsyncClient(
            auth=_BearerAuth(credential),
            timeout=httpx.Timeout(30.0, read=300.0),
            follow_redirects=True,
        ) as http_client,
        streamable_http_client(
            url=os.environ["FOUNDRY_TOOLBOX_MCP_SERVER_URL"],
            http_client=http_client,
        ) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        # Discover skills served by the toolbox and inject them as a context provider.
        skills_provider = SkillsProvider(MCPSkillsSource(client=session))

        async with Agent(
            client=FoundryChatClient(credential=credential),
            name="ToolboxMCPSkillsAgent",
            instructions="You are a helpful assistant. Use available skills to answer the user.",
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
