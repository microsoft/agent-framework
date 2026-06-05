# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from collections.abc import Callable, Generator

import httpx
from agent_framework import Agent, MCPSkillsSource, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

# Load environment variables from .env file
load_dotenv()


class ToolboxAuth(httpx.Auth):
    """Attach a fresh Foundry bearer token to every request."""

    def __init__(self, token_provider: Callable[[], str]):
        self._get_token = token_provider

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


async def main() -> None:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    deployment = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    toolbox_name = os.environ["TOOLBOX_NAME"]

    # Build the Toolbox MCP URL from the project endpoint and toolbox name.
    toolbox_mcp_url = f"{project_endpoint.rstrip('/')}/toolboxes/{toolbox_name}/mcp?api-version=v1"

    credential = DefaultAzureCredential()

    # Create a token provider for Foundry bearer auth
    token_provider = get_bearer_token_provider(credential, "https://ai.azure.com/.default")

    # ── Connect to the Foundry Toolbox MCP endpoint ──────────────────────────
    # Create an HTTP client that attaches a fresh Foundry bearer token to every
    # request and advertises the toolbox preview feature flag.
    async with (
        httpx.AsyncClient(
            auth=ToolboxAuth(token_provider),
            headers={"Foundry-Features": "Toolboxes=V1Preview"},
            timeout=httpx.Timeout(30.0, read=300.0),
            follow_redirects=True,
        ) as http_client,
        streamable_http_client(
            url=toolbox_mcp_url,
            http_client=http_client,
        ) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        print(f"Connected to Foundry Toolbox '{toolbox_name}' MCP server.")

        # ── Configure MCP-based skills provider ──────────────────────────────
        # MCPSkillsSource reads skill://index.json and creates one MCPSkill per
        # skill-md entry; SKILL.md bodies are fetched on demand via
        # resources/read.
        skills_provider = SkillsProvider(MCPSkillsSource(client=session))

        # ── Create the agent ─────────────────────────────────────────────────
        client = FoundryChatClient(
            project_endpoint=project_endpoint,
            model=deployment,
            credential=credential,
        )

        agent = Agent(
            client=client,
            name=os.environ.get("AGENT_NAME", "hosted-toolbox-mcp-skills"),
            instructions="You are a helpful assistant.",
            context_providers=[skills_provider],
            # History will be managed by the hosting infrastructure, thus there
            # is no need to store history by the service. Learn more at:
            # https://developers.openai.com/api/reference/resources/responses/methods/create
            default_options={"store": False},
        )

        # ── Build and run the host ───────────────────────────────────────────
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
