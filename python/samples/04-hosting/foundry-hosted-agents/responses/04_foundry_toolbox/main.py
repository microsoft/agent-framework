# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from collections.abc import Callable

import httpx
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def resolve_toolbox_endpoint() -> str:
    """Resolve the toolbox MCP endpoint URL.

    Prefers the explicit ``FOUNDRY_TOOLBOX_ENDPOINT`` env var; falls back to
    constructing the URL from ``FOUNDRY_PROJECT_ENDPOINT`` and ``TOOLBOX_NAME``
    (the variables injected by the Foundry hosting scaffolding after ``azd provision``).
    """
    if (endpoint := os.environ.get("FOUNDRY_TOOLBOX_ENDPOINT")) is not None:
        if not endpoint:
            raise ValueError("FOUNDRY_TOOLBOX_ENDPOINT is set but empty")
        return endpoint
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    toolbox_name = os.environ["TOOLBOX_NAME"]
    return f"{project_endpoint}/toolboxes/{toolbox_name}/versions/29/mcp?api-version=v1"


class ToolboxAuth(httpx.Auth):
    """Injects a fresh bearer token on every request."""

    def __init__(self, token_provider: Callable[[], str]):
        self._get_token = token_provider

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


async def main():
    credential = DefaultAzureCredential()

    # Create the toolbox
    token_provider = get_bearer_token_provider(credential, "https://ai.azure.com/.default")

    http_client = httpx.AsyncClient(
        auth=ToolboxAuth(token_provider),
        headers={"Foundry-Features": "Toolboxes=V1Preview"},
        timeout=120.0,
    )

    toolbox = MCPStreamableHTTPTool(
        name=os.environ.get("TOOLBOX_NAME", "toolbox"),
        url=resolve_toolbox_endpoint(),
        http_client=http_client,
        load_prompts=False,
    )

    # Create the chat client
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    async with Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        tools=toolbox,
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    ) as agent:
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
