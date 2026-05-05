# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, select_toolbox_tools
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Foundry Chat Client with Toolbox Example

This sample demonstrates loading a named, versioned Foundry toolbox into an
Agent via ``FoundryChatClient.get_toolbox()``. A toolbox is a server-side
bundle of tool configurations (code interpreter, file search, MCP, web search,
etc.) configured in the Foundry portal or via the raw SDK.

Prerequisites:
- A Microsoft Foundry project
- A toolbox already configured in that project (set TOOLBOX_NAME below)
- FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL environment variables set
"""

# Replace with your own Foundry toolbox name and version.
TOOLBOX_NAME = "research_toolbox"
TOOLBOX_VERSION = "1"
# Used only by combine_toolboxes() — swap in a second toolbox you own.
SECOND_TOOLBOX_NAME = "analysis_toolbox"
SECOND_TOOLBOX_VERSION = "1"

# Replace with any question that exercises the tools configured in your toolbox.
QUERY = "Introduce yourself and briefly describe the tools you can use to help me."


def create_sample_toolbox(name: str) -> str:
    """Create (or replace) a toolbox version in the Foundry project.

    Toolboxes are normally configured in the Foundry portal or a deployment
    script, not the application itself. This helper exists so the samples can
    be run end-to-end without first setting a toolbox up by hand — delete any
    existing toolbox under ``name``, then create a fresh version containing an
    MCP tool, a web search tool, and a code interpreter tool. Returns the
    created version identifier.
    """
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import CodeInterpreterTool, MCPTool, Tool, WebSearchTool
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

        tools.append(WebSearchTool(name="web_search"))
        tools.append(CodeInterpreterTool(name="code_interpreter"))

        created = project_client.beta.toolboxes.create_version(
            name=name,
            description="Toolbox version with MCP require_approval set to 'never'.",
            tools=tools,
        )
        print(f"Created toolbox {created.name}@{created.version} ({len(created.tools)} tool(s))")
        return created.version


async def main() -> None:
    """Example showing how to use a single Foundry toolbox with FoundryChatClient."""
    print("=== Foundry Chat Client with Toolbox Example ===")

    # For authentication, run `az login` in your terminal or replace
    # AzureCliCredential with your preferred authentication option.
    client = FoundryChatClient(
        credential=AzureCliCredential(),
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
    )

    # Comment out if the toolbox already exists in your Foundry project.
    create_sample_toolbox(TOOLBOX_NAME)

    # Omit ``version`` to resolve the toolbox's current default version at runtime.
    toolbox = await client.get_toolbox(TOOLBOX_NAME)
    print(f"Loaded toolbox {toolbox.name}@{toolbox.version} ({len(toolbox.tools)} tool(s))")

    agent = Agent(
        client=client,
        instructions="You are a research assistant. Use the available tools to answer questions.",
        tools=toolbox,
    )

    print(f"User: {QUERY}")
    result = await agent.run(QUERY)
    print(f"Result: {result}\n")


async def combine_toolboxes() -> None:
    """Alternative flow: combine the tools from multiple Foundry toolboxes."""
    client = FoundryChatClient(
        credential=AzureCliCredential(),
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
    )

    # Comment out if the toolboxes already exist in your Foundry project.
    create_sample_toolbox(TOOLBOX_NAME)
    create_sample_toolbox(SECOND_TOOLBOX_NAME)

    toolbox_a = await client.get_toolbox(TOOLBOX_NAME, version=TOOLBOX_VERSION)
    toolbox_b = await client.get_toolbox(SECOND_TOOLBOX_NAME, version=SECOND_TOOLBOX_VERSION)
    print(
        "Loaded toolboxes: "
        f"{toolbox_a.name}@{toolbox_a.version} ({len(toolbox_a.tools)} tool(s)), "
        f"{toolbox_b.name}@{toolbox_b.version} ({len(toolbox_b.tools)} tool(s))"
    )

    agent = Agent(
        client=client,
        instructions="You are a research assistant. Use all available tools to answer questions.",
        tools=[toolbox_a, toolbox_b],
    )

    print(f"User: {QUERY}")
    result = await agent.run(QUERY)
    print(f"Combined-toolbox result: {result}\n")


async def select_tools_from_toolbox() -> None:
    """Alternative flow: keep only a subset of toolbox tools before agent creation."""
    client = FoundryChatClient(
        credential=AzureCliCredential(),
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
    )

    # Comment out if the toolbox already exists in your Foundry project.
    create_sample_toolbox(TOOLBOX_NAME)

    toolbox = await client.get_toolbox(TOOLBOX_NAME, version=TOOLBOX_VERSION)
    print(f"Loaded toolbox {toolbox.name}@{toolbox.version} ({len(toolbox.tools)} tool(s))")

    selected_tools = select_toolbox_tools(
        toolbox,
        include_types=["code_interpreter", "mcp"],
    )
    print(f"Selected {len(selected_tools)} toolbox tools for the agent")

    agent = Agent(
        client=client,
        instructions="You are a research assistant. Use only the selected toolbox tools.",
        tools=selected_tools,
    )

    print(f"User: {QUERY}")
    result = await agent.run(QUERY)
    print(f"Selected-toolbox result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
    # asyncio.run(combine_toolboxes())
    # asyncio.run(select_tools_from_toolbox())
