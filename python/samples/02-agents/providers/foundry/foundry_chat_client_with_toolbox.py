# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from collections.abc import Callable
from typing import Any, cast

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
- Azure CLI authentication (``az login``)

The helper publishes a version with tool search enabled and connects to that exact
version. The model initially sees tool_search and call_tool, then discovers the
underlying MCP tools as needed. Each run creates a version; existing versions are
not deleted. Remove ToolSearchToolboxTool() to compare the full initial tool list.
"""

TOOLBOX_NAME = "research_toolbox"


def create_sample_toolbox(name: str) -> str:
    """Create a toolbox version with tool search in the Foundry project.

    Toolboxes are normally configured in the Foundry portal or a deployment
    script, not the application itself. This helper exists so the sample can
    be run end-to-end without first setting a toolbox up by hand. Returns the
    created version identifier without deleting existing versions.
    """
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import MCPToolboxTool, ToolboxTool, ToolSearchToolboxTool

    with (
        AzureCliCredential() as credential,
        AIProjectClient(credential=credential, endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"]) as project_client,
    ):
        toolboxes = getattr(project_client, "toolboxes", None)
        if toolboxes is None:
            toolboxes = cast(Any, project_client.beta).toolboxes

        tools: list[ToolboxTool] = [
            MCPToolboxTool(
                server_label="api_specs",
                server_url="https://gitmcp.io/Azure/azure-rest-api-specs",
                require_approval="never",
            ),
            ToolSearchToolboxTool(),
        ]

        created = toolboxes.create_version(
            name=name,
            description="Toolbox version with MCP tools discovered through tool search.",
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

    # Connect to the new version so the tool-search configuration is unambiguous.
    version = create_sample_toolbox(TOOLBOX_NAME)
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")

    toolbox_tool = MCPStreamableHTTPTool(
        name="foundry_toolbox",
        description="Tools exposed by the configured Foundry toolbox",
        url=f"{project_endpoint}/toolboxes/{TOOLBOX_NAME}/versions/{version}/mcp?api-version=v1",
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
        query = "Find the REST API documentation for Azure Container Apps session pools."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Assistant: {result}")


if __name__ == "__main__":
    asyncio.run(main())
