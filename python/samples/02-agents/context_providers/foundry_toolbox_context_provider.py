# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Any

from agent_framework import Agent, AgentSession, ContextProvider, Message, SessionContext
from agent_framework.foundry import (
    FoundryChatClient,
    get_toolbox_tool_name,
    get_toolbox_tool_type,
    select_toolbox_tools,
)
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()

"""
Foundry Toolbox + Context Provider Example

This sample composes a Foundry toolbox with a ContextProvider so the agent's
tool list is chosen dynamically per-turn. It uses the chat client itself as a lightweight "tool router": the
latest user message plus a short menu of toolbox tools is sent to the model
with a Pydantic ``response_format``, and the returned tool names drive
``select_toolbox_tools``. The toolbox is fetched once and cached on the
provider's state dict; subsequent turns reuse the cache.

Prerequisites:
- A Microsoft Foundry project
- A toolbox already configured in that project (set TOOLBOX_NAME below)
- FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL environment variables set
- Azure CLI authentication (`az login`)
"""

# Replace with your own Foundry toolbox name and version.
TOOLBOX_NAME = "research_toolbox"
# Set to None to resolve the toolbox's current default version at fetch time.
TOOLBOX_VERSION: str | None = None

# Generic queries that exercise the router without assuming any specific tool
# types are configured. The first is introspective, the second forces a
# non-empty pick for whichever tools the toolbox actually contains, and the
# third should route to nothing.
QUERIES: list[str] = [
    "Introduce yourself and briefly describe the tools you can use to help me.",
    "Pick the tool you think is most useful and demonstrate it with a short example.",
    "Say hi in one short sentence - no tools needed.",
]


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


class ToolSelection(BaseModel):
    """Structured output for the per-turn tool router."""

    tool_names: list[str]


ROUTER_INSTRUCTIONS = (
    "You are a tool router. Given the user's latest message and a menu of "
    "available tools (one per line, formatted as 'NAME - TYPE'), return the "
    "NAMES of the tools that would plausibly help answer the message. Return "
    "an empty list if no tool is needed."
)


class DynamicToolboxProvider(ContextProvider):
    """Fetches a Foundry toolbox once and lets the model pick tools per-turn."""

    DEFAULT_SOURCE_ID = "foundry_toolbox"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        client: FoundryChatClient,
        toolbox_name: str,
        toolbox_version: str | None = None,
    ) -> None:
        super().__init__(source_id)
        self._client = client
        self._toolbox_name = toolbox_name
        self._toolbox_version = toolbox_version

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Cache the toolbox on first call, then let the model pick tools per-turn."""
        toolbox = state.get("toolbox")
        if toolbox is None:
            toolbox = await self._client.get_toolbox(self._toolbox_name, version=self._toolbox_version)
            state["toolbox"] = toolbox
            print(f"[{self.source_id}] Loaded toolbox {toolbox.name}@{toolbox.version} ({len(toolbox.tools)} tool(s))")

        user_messages = [m for m in context.get_messages(include_input=True) if getattr(m, "role", None) == "user"]
        if not user_messages:
            context.extend_tools(self.source_id, list(toolbox.tools))
            return

        picks = await self._route_tools(user_messages[-1].text, toolbox.tools)
        if picks:
            tools = select_toolbox_tools(toolbox, include_names=picks)
            print(f"[{self.source_id}] Router picked {sorted(picks)} - surfacing {len(tools)} tool(s)")
        else:
            tools = list(toolbox.tools)
            print(f"[{self.source_id}] Router picked nothing - surfacing all {len(tools)} tool(s)")
        context.extend_tools(self.source_id, tools)

    async def _route_tools(self, user_text: str, tools: Any) -> list[str]:
        """Ask the model which toolbox tools to surface for this turn."""
        menu = "\n".join(f"- {get_toolbox_tool_name(t)} - {get_toolbox_tool_type(t)}" for t in tools)
        prompt = (
            f"User message:\n{user_text}\n\n"
            f"Available tools:\n{menu}\n\n"
            "Return the names of tools that should be surfaced for this turn."
        )
        response = await self._client.get_response(
            messages=[Message("user", [prompt])],
            options={
                "instructions": ROUTER_INSTRUCTIONS,
                "response_format": ToolSelection,
            },
        )
        selection: ToolSelection = response.value  # type: ignore
        return selection.tool_names


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # Comment out if the toolbox already exists in your Foundry project.
    create_sample_toolbox(TOOLBOX_NAME)

    toolbox_provider = DynamicToolboxProvider(
        client=client,
        toolbox_name=TOOLBOX_NAME,
        toolbox_version=TOOLBOX_VERSION,
    )

    async with Agent(
        client=client,
        instructions=(
            "You are a helpful assistant. Use the tools available to you on each "
            "turn to answer the user. If no tools are relevant, reply directly."
        ),
        context_providers=[toolbox_provider],
    ) as agent:
        session = agent.create_session()

        for query in QUERIES:
            print(f"\nUser: {query}")
            result = await agent.run(query, session=session)
            print(f"Assistant: {result}")


if __name__ == "__main__":
    asyncio.run(main())
