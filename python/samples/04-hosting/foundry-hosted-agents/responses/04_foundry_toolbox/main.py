# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from collections.abc import Callable
from typing import Any

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def _resolve_toolbox_endpoint() -> str:
    """Resolve the toolbox MCP endpoint URL.

    Prefers the explicit ``FOUNDRY_TOOLBOX_ENDPOINT`` env var; falls back to
    constructing the URL from ``FOUNDRY_PROJECT_ENDPOINT`` and ``TOOLBOX_NAME``
    (the variables injected by the Foundry hosting scaffolding after ``azd provision``).
    """
    if endpoint := os.environ.get("FOUNDRY_TOOLBOX_ENDPOINT"):
        return endpoint
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    toolbox_name = os.environ["TOOLBOX_NAME"]
    return f"{project_endpoint}/toolsets/{toolbox_name}/mcp?api-version=v1"


def make_toolbox_header_provider(credential: TokenCredential) -> Callable[[dict[str, Any]], dict[str, str]]:
    """Build a header_provider that injects a fresh Azure AI bearer token on every MCP request."""
    get_token = get_bearer_token_provider(credential, "https://ai.azure.com/.default")

    def provide(_kwargs: dict[str, Any]) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {get_token()}",
        }

    return provide


async def main():
    credential = DefaultAzureCredential()

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    toolbox_tool = MCPStreamableHTTPTool(
        name="foundry_toolbox",
        description="Tools exposed by the configured Foundry toolbox",
        url=_resolve_toolbox_endpoint(),
        header_provider=make_toolbox_header_provider(credential),
        load_prompts=False,
    )

    async with Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        tools=toolbox_tool,
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    ) as agent:
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
