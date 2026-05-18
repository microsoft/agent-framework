# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from collections.abc import Callable
from typing import Any

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.core.credentials import TokenCredential
from azure.identity import AzureCliCredential, DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Foundry Toolbox via MAF ``MCPStreamableHTTPTool``

Instead of fetching the toolbox and fanning out individual tool specs, point
MAF's ``MCPStreamableHTTPTool`` at the toolbox's MCP endpoint. The agent
discovers and calls the toolbox's tools over MCP at runtime.

Prerequisites:
- A Microsoft Foundry project with a toolbox configured
- FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL environment variables set
- FOUNDRY_TOOLBOX_ENDPOINT: the toolbox's MCP endpoint URL, e.g.
  ``https://<account>.services.ai.azure.com/api/projects/<project>/toolsets/<name>/mcp?api-version=v1``
- Azure CLI authentication (``az login``)
"""

# Must match the ``<name>`` segment of FOUNDRY_TOOLBOX_ENDPOINT.
TOOLBOX_NAME = "research_toolbox"


def create_sample_toolbox(name: str) -> str:
    """Create (or replace) a toolbox version in the Foundry project.

    Toolboxes are normally configured in the Foundry portal or a deployment
    script, not the application itself. This helper exists so the sample can
    be run end-to-end without first setting a toolbox up by hand — delete any
    existing toolbox under ``name``, then create a fresh version containing a
    single MCP tool. Returns the created version identifier.
    """
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import MCPTool, Tool
    from azure.core.exceptions import ResourceNotFoundError

    with (
        AzureCliCredential() as credential,
        AIProjectClient(credential=credential, endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"]) as project_client,
    ):
        try:
            project_client.beta.toolboxes.delete(name)
            print(f"Toolbox `{name}` deleted")
        except ResourceNotFoundError:
            pass

        tools: list[Tool] = [
            MCPTool(
                server_label="api_specs",
                server_url="https://gitmcp.io/Azure/azure-rest-api-specs",
                require_approval="never",
            )
        ]

        created = project_client.beta.toolboxes.create_version(
            name=name,
            description="Toolbox version with MCP require_approval set to 'never'.",
            tools=tools,
        )
        print(f"Created toolbox {created.name}@{created.version} ({len(created.tools)} tool(s))")
        return created.version


def make_toolbox_header_provider(credential: TokenCredential) -> Callable[[dict[str, Any]], dict[str, str]]:
    """Build a header_provider that injects a fresh Azure AI bearer token on every MCP request."""
    get_token = get_bearer_token_provider(credential, "https://ai.azure.com/.default")

    def provide(_kwargs: dict[str, Any]) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {get_token()}",
        }

    return provide


async def main() -> None:
    credential = DefaultAzureCredential()

    # Comment out if the toolbox already exists in your Foundry project.
    create_sample_toolbox(TOOLBOX_NAME)

    toolbox_tool = MCPStreamableHTTPTool(
        name="foundry_toolbox",
        description="Tools exposed by the configured Foundry toolbox",
        url=os.environ["FOUNDRY_TOOLBOX_ENDPOINT"],
        header_provider=make_toolbox_header_provider(credential),
        load_prompts=False,
    )

    async with Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=credential,
        ),
        instructions="You are a helpful assistant. Use the available toolbox tools to answer the user.",
        tools=toolbox_tool,
    ) as agent:
        query = "What tools do you have access to?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Assistant: {result}")


if __name__ == "__main__":
    asyncio.run(main())
