# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for toolbox helpers on FoundryChatClient.

Return types are the raw azure-ai-projects SDK models (ToolboxVersionObject,
ToolboxObject) — no custom wrapper. Tests verify the chat-client get path and
tool-selection ergonomics.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from azure.ai.projects.models import (
        AutoCodeInterpreterToolParam,
        CodeInterpreterTool,
        Tool,
        ToolboxObject,
        ToolboxVersionObject,
    )
except ImportError:
    pytest.skip(
        "Toolbox types require azure-ai-projects>=2.1.0 (unreleased).",
        allow_module_level=True,
    )

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


class _AsyncIter:
    """Minimal async-iterable for mocking ``AsyncItemPaged`` in tests."""

    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def __aiter__(self) -> _AsyncIter:
        self._iter = iter(self._items)
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


def _make_code_interpreter() -> CodeInterpreterTool:
    return CodeInterpreterTool(container=AutoCodeInterpreterToolParam())


def _make_version_object(
    *,
    name: str = "research_tools",
    version: str = "v1",
    tools: list[Tool] | None = None,
    description: str | None = None,
) -> ToolboxVersionObject:
    return ToolboxVersionObject(
        id=f"tbv_{name}_{version}",
        name=name,
        version=version,
        metadata={},
        created_at=dt.datetime(2026, 4, 10, tzinfo=dt.timezone.utc),
        tools=tools if tools is not None else [_make_code_interpreter()],
        description=description,
    )


def _make_mock_foundry_client(*, project_client: MagicMock) -> Any:
    """Build a FoundryChatClient wired to a mock project_client."""
    from agent_framework_foundry import FoundryChatClient

    project_client.get_openai_client = MagicMock(return_value=MagicMock())
    return FoundryChatClient(project_client=project_client, model="test-model")


# --------------------------------------------------------------------------- #
# get_toolbox — explicit version path                                         #
# --------------------------------------------------------------------------- #


async def test_get_toolbox_with_explicit_version_makes_single_request() -> None:
    project_client = MagicMock()
    version_obj = _make_version_object(name="research_tools", version="v3")
    project_client.beta.toolboxes.get_version = AsyncMock(return_value=version_obj)
    project_client.beta.toolboxes.get = AsyncMock(
        side_effect=AssertionError("get() must not be called when version is explicit")
    )

    client = _make_mock_foundry_client(project_client=project_client)

    toolbox = await client.get_toolbox("research_tools", version="v3")

    assert isinstance(toolbox, ToolboxVersionObject)
    assert toolbox.name == "research_tools"
    assert toolbox.version == "v3"
    project_client.beta.toolboxes.get_version.assert_awaited_once_with("research_tools", "v3")
    project_client.beta.toolboxes.get.assert_not_called()


# --------------------------------------------------------------------------- #
# get_toolbox — default-version path + error + passthrough + smoke            #
# --------------------------------------------------------------------------- #


async def test_get_toolbox_default_version_resolves_then_fetches() -> None:
    project_client = MagicMock()
    handle = ToolboxObject(id="tb_1", name="research_tools", default_version="v5")
    version_obj = _make_version_object(name="research_tools", version="v5")

    project_client.beta.toolboxes.get = AsyncMock(return_value=handle)
    project_client.beta.toolboxes.get_version = AsyncMock(return_value=version_obj)

    client = _make_mock_foundry_client(project_client=project_client)

    toolbox = await client.get_toolbox("research_tools")

    assert toolbox.version == "v5"
    project_client.beta.toolboxes.get.assert_awaited_once_with("research_tools")
    project_client.beta.toolboxes.get_version.assert_awaited_once_with("research_tools", "v5")


async def test_get_toolbox_propagates_resource_not_found() -> None:
    project_client = MagicMock()
    project_client.beta.toolboxes.get = AsyncMock(side_effect=ResourceNotFoundError("no such toolbox"))

    client = _make_mock_foundry_client(project_client=project_client)

    with pytest.raises(ResourceNotFoundError):
        await client.get_toolbox("missing_toolbox")


async def test_get_toolbox_tool_passthrough_preserves_heterogeneous_types() -> None:
    """Ensure all Tool subclasses pass through unchanged — critical for MCP tools
    with project_connection_id, which must reach the runtime untouched."""
    from azure.ai.projects.models import MCPTool as FoundryMCPTool

    mcp_tool = FoundryMCPTool(
        server_label="github_oauth",
        server_url="https://api.githubcopilot.com/mcp",
    )
    mcp_tool["project_connection_id"] = "conn_abc"

    project_client = MagicMock()
    version_obj = _make_version_object(
        name="mixed",
        version="v1",
        tools=[_make_code_interpreter(), mcp_tool],
    )
    project_client.beta.toolboxes.get_version = AsyncMock(return_value=version_obj)

    client = _make_mock_foundry_client(project_client=project_client)

    toolbox = await client.get_toolbox("mixed", version="v1")

    assert len(toolbox.tools) == 2
    assert isinstance(toolbox.tools[0], CodeInterpreterTool)
    assert isinstance(toolbox.tools[1], FoundryMCPTool)
    assert toolbox.tools[1]["project_connection_id"] == "conn_abc"


async def test_toolbox_tools_can_be_passed_to_agent() -> None:
    """Integration smoke: toolbox.tools can be passed directly to Agent(tools=...) ."""
    from agent_framework import Agent

    project_client = MagicMock()
    version_obj = _make_version_object(name="research_tools", version="v1", tools=[_make_code_interpreter()])
    project_client.beta.toolboxes.get_version = AsyncMock(return_value=version_obj)

    client = _make_mock_foundry_client(project_client=project_client)

    toolbox = await client.get_toolbox("research_tools", version="v1")

    agent = Agent(
        client=client,
        instructions="You are a test agent.",
        tools=toolbox.tools,
    )

    agent_tools = agent.default_options["tools"]
    assert len(agent_tools) == 1
    assert agent_tools[0]["type"] == "code_interpreter"


async def test_multiple_toolbox_tool_lists_can_be_combined_in_agent() -> None:
    """Nested toolbox ``.tools`` lists flatten into one tool list on Agent construction."""
    from agent_framework import Agent

    project_client = MagicMock()
    project_client.get_openai_client = MagicMock(return_value=MagicMock())
    client = _make_mock_foundry_client(project_client=project_client)

    toolbox_a = _make_version_object(name="research_tools", version="v1", tools=[_make_code_interpreter()])
    toolbox_b = _make_version_object(name="some_other_tools", version="v3", tools=[_make_code_interpreter()])

    agent = Agent(
        client=client,
        instructions="You are a test agent.",
        tools=[toolbox_a.tools, toolbox_b.tools],
    )

    agent_tools = agent.default_options["tools"]
    assert len(agent_tools) == 2
    assert agent_tools[0]["type"] == "code_interpreter"
    assert agent_tools[1]["type"] == "code_interpreter"


# --------------------------------------------------------------------------- #
# toolbox tool selection helpers                                              #
# --------------------------------------------------------------------------- #


def test_get_toolbox_tool_name_prefers_server_label_then_name_then_type() -> None:
    from azure.ai.projects.models import MCPTool as FoundryMCPTool

    from agent_framework_foundry import get_toolbox_tool_name

    mcp_tool = FoundryMCPTool(
        server_label="githubmcp",
        server_url="https://api.githubcopilot.com/mcp",
    )
    assert get_toolbox_tool_name(mcp_tool) == "githubmcp"

    named_tool = {"type": "code_interpreter", "name": "ci_tool"}
    assert get_toolbox_tool_name(named_tool) == "ci_tool"

    unnamed_tool = {"type": "web_search"}
    assert get_toolbox_tool_name(unnamed_tool) == "web_search"


def test_select_toolbox_tools_filters_by_names() -> None:
    from azure.ai.projects.models import MCPTool as FoundryMCPTool

    from agent_framework_foundry import select_toolbox_tools

    tools: list[Tool | dict[str, Any]] = [
        FoundryMCPTool(server_label="githubmcp", server_url="https://api.githubcopilot.com/mcp"),
        {"type": "code_interpreter", "name": "python_runner"},
        {"type": "web_search"},
    ]

    selected = select_toolbox_tools(tools, include_names=["githubmcp", "python_runner"])

    assert len(selected) == 2
    assert selected[0] is tools[0]
    assert selected[1] is tools[1]


def test_select_toolbox_tools_filters_by_typed_tool_types() -> None:
    from agent_framework_foundry import select_toolbox_tools

    tools: list[Tool | dict[str, Any]] = [
        {"type": "mcp", "server_label": "githubmcp"},
        {"type": "code_interpreter", "name": "python_runner"},
        {"type": "web_search"},
    ]

    selected = select_toolbox_tools(tools, include_types=["mcp", "code_interpreter"])

    assert len(selected) == 2
    assert selected[0]["type"] == "mcp"
    assert selected[1]["type"] == "code_interpreter"


def test_select_toolbox_tools_accepts_toolbox_object_directly() -> None:
    from agent_framework_foundry import select_toolbox_tools

    toolbox = _make_version_object(
        name="research_tools",
        version="v1",
        tools=[
            {"type": "mcp", "server_label": "githubmcp"},  # type: ignore[list-item]
            {"type": "code_interpreter", "name": "python_runner"},  # type: ignore[list-item]
            {"type": "web_search"},  # type: ignore[list-item]
        ],
    )

    selected = select_toolbox_tools(toolbox, include_types=["mcp", "code_interpreter"])

    assert len(selected) == 2
    assert selected[0]["type"] == "mcp"
    assert selected[1]["type"] == "code_interpreter"


async def test_fetched_toolbox_can_be_combined_with_function_tool() -> None:
    from agent_framework import Agent, FunctionTool, tool

    project_client = MagicMock()
    version_obj = _make_version_object(name="research_tools", version="v1", tools=[_make_code_interpreter()])
    project_client.beta.toolboxes.get_version = AsyncMock(return_value=version_obj)

    client = _make_mock_foundry_client(project_client=project_client)
    toolbox = await client.get_toolbox("research_tools", version="v1")

    @tool(name="local_lookup", description="A local helper tool")
    def local_lookup(query: str) -> str:
        return query

    agent = Agent(
        client=client,
        instructions="You are a test agent.",
        tools=[toolbox, local_lookup],
    )

    agent_tools = agent.default_options["tools"]
    assert len(agent_tools) == 2
    assert agent_tools[0]["type"] == "code_interpreter"
    assert isinstance(agent_tools[1], FunctionTool)
    assert agent_tools[1].name == "local_lookup"


def test_select_toolbox_tools_supports_excludes_and_predicate() -> None:
    from agent_framework_foundry import select_toolbox_tools

    tools: list[Tool | dict[str, Any]] = [
        {"type": "mcp", "server_label": "githubmcp"},
        {"type": "mcp", "server_label": "learnmcp"},
        {"type": "web_search"},
    ]

    selected = select_toolbox_tools(
        tools,
        exclude_names=["learnmcp"],
        predicate=lambda tool: tool.get("type") == "mcp",  # type: ignore[union-attr]
    )

    assert len(selected) == 1
    assert selected[0]["server_label"] == "githubmcp"


async def test_selected_toolbox_subset_can_be_combined_with_function_tool() -> None:
    from agent_framework import Agent, FunctionTool, tool

    from agent_framework_foundry import select_toolbox_tools

    project_client = MagicMock()
    version_obj = _make_version_object(
        name="research_tools",
        version="v1",
        tools=[
            {"type": "mcp", "server_label": "githubmcp"},  # type: ignore[list-item]
            {"type": "code_interpreter", "name": "python_runner"},  # type: ignore[list-item]
            {"type": "web_search"},  # type: ignore[list-item]
        ],
    )
    project_client.beta.toolboxes.get_version = AsyncMock(return_value=version_obj)

    client = _make_mock_foundry_client(project_client=project_client)
    toolbox = await client.get_toolbox("research_tools", version="v1")
    selected_tools = select_toolbox_tools(toolbox, include_types=["mcp", "code_interpreter"])

    @tool(name="local_lookup", description="A local helper tool")
    def local_lookup(query: str) -> str:
        return query

    agent = Agent(
        client=client,
        instructions="You are a test agent.",
        tools=[selected_tools, local_lookup],
    )

    agent_tools = agent.default_options["tools"]
    assert len(agent_tools) == 3
    assert agent_tools[0]["type"] == "mcp"
    assert agent_tools[1]["type"] == "code_interpreter"
    assert isinstance(agent_tools[2], FunctionTool)
    assert agent_tools[2].name == "local_lookup"


# --------------------------------------------------------------------------- #
# Integration                                                                 #
# --------------------------------------------------------------------------- #


skip_if_foundry_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("FOUNDRY_PROJECT_ENDPOINT", "") in ("", "https://test-project.services.ai.azure.com/")
    or os.getenv("FOUNDRY_MODEL", "") == "",
    reason="No real FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_MODEL provided; skipping integration tests.",
)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_foundry_integration_tests_disabled
async def test_integration_get_toolbox_round_trip_against_real_project() -> None:
    """Create a toolbox via the raw SDK, fetch via FoundryChatClient, then delete.

    Self-contained to avoid depending on toolboxes that may be cleaned up
    externally. Exercises both the default-version resolution path
    (``get`` + ``get_version``) and the explicit-version path.
    """
    from uuid import uuid4

    from agent_framework import Agent

    from agent_framework_foundry import FoundryChatClient

    client = FoundryChatClient(credential=AzureCliCredential())
    project_client = client.project_client

    toolbox_name = f"af-int-toolbox-{uuid4().hex[:12]}"
    created = await project_client.beta.toolboxes.create_version(
        name=toolbox_name,
        tools=[CodeInterpreterTool()],
        description=f"{toolbox_name} integration test",
    )
    assert isinstance(created, ToolboxVersionObject)
    try:
        toolbox_default = await client.get_toolbox(toolbox_name)
        assert toolbox_default.name == toolbox_name
        assert toolbox_default.tools, "Default-version fetch returned no tools"

        toolbox_pinned = await client.get_toolbox(toolbox_name, version=created.version)
        assert toolbox_pinned.version == created.version
        assert toolbox_pinned.tools

        agent = Agent(
            client=client,
            instructions="You are a test agent.",
            tools=toolbox_pinned.tools,
        )
        assert len(agent.default_options["tools"]) == len(toolbox_pinned.tools)
    finally:
        await project_client.beta.toolboxes.delete(toolbox_name)
