# Copyright (c) Microsoft. All rights reserved.

"""Shared tool helpers for Foundry chat clients.

Includes:

* *Toolbox* helpers — a *toolbox* is a named, versioned bundle of tool
  definitions stored in an Azure AI Foundry project.
* Responses-API payload sanitization for Foundry hosted tools.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, cast

from agent_framework._feature_stage import ExperimentalFeature, experimental
from azure.ai.projects.models import MCPTool as FoundryMCPTool

if TYPE_CHECKING:
    from azure.ai.projects.aio import AIProjectClient
    from azure.ai.projects.models import Tool, ToolboxVersionObject

FoundryHostedToolType: TypeAlias = (
    Literal[
        "code_interpreter",
        "file_search",
        "image_generation",
        "mcp",
        "web_search",
    ]
    | str
)
ToolboxToolSelectionInput: TypeAlias = "ToolboxVersionObject | Sequence[Tool | dict[str, Any]]"


@experimental(feature_id=ExperimentalFeature.TOOLBOXES)
async def fetch_toolbox(
    project_client: AIProjectClient,
    name: str,
    version: str | None = None,
) -> ToolboxVersionObject:
    """Fetch a toolbox version via an ``AIProjectClient``.

    If ``version`` is omitted, resolves the toolbox's current default
    version (two requests: one to ``.get(name)`` for the default version
    pointer, one to ``.get_version(name, version)`` for the tools). If
    ``version`` is specified, fetches that version directly (single request).
    """
    if version is None:
        handle = await project_client.beta.toolboxes.get(name)
        version = handle.default_version
    return await project_client.beta.toolboxes.get_version(name, version)


@experimental(feature_id=ExperimentalFeature.TOOLBOXES)
def get_toolbox_tool_name(tool: Tool | dict[str, Any]) -> str | None:
    """Return the best-effort display/selection name for a toolbox tool.

    Selection precedence:
    1. MCP ``server_label``
    2. Generic tool ``name``
    3. Tool ``type``
    """
    if isinstance(tool, dict):
        if server_label := tool.get("server_label"):
            return str(server_label)
        if name := tool.get("name"):
            return str(name)
        if tool_type := tool.get("type"):
            return str(tool_type)
        return None

    if server_label := getattr(tool, "server_label", None):
        return str(server_label)
    if name := getattr(tool, "name", None):
        return str(name)
    if tool_type := getattr(tool, "type", None):
        return str(tool_type)
    return None


@experimental(feature_id=ExperimentalFeature.TOOLBOXES)
def get_toolbox_tool_type(tool: Tool | dict[str, Any]) -> str | None:
    """Return the raw tool ``type`` if present."""
    tool_type = tool.get("type") if isinstance(tool, dict) else getattr(tool, "type", None)
    return str(tool_type) if tool_type is not None else None


@experimental(feature_id=ExperimentalFeature.TOOLBOXES)
def select_toolbox_tools(
    tools: ToolboxToolSelectionInput,
    *,
    include_names: Collection[str] | None = None,
    exclude_names: Collection[str] | None = None,
    include_types: Collection[FoundryHostedToolType] | None = None,
    exclude_types: Collection[FoundryHostedToolType] | None = None,
    predicate: Callable[[Tool | dict[str, Any]], bool] | None = None,
) -> list[Tool | dict[str, Any]]:
    """Filter toolbox tools by normalized name, raw type, and/or predicate.

    Normalized name precedence:
    1. ``server_label`` for MCP tools
    2. ``name``
    3. ``type``
    """
    tool_items: Sequence[Tool | dict[str, Any]] = (
        tools if isinstance(tools, Sequence) else cast("Sequence[Tool | dict[str, Any]]", tools.tools)
    )
    include_name_set = {str(item) for item in include_names} if include_names is not None else None
    exclude_name_set = {str(item) for item in exclude_names} if exclude_names is not None else None
    include_type_set = {str(item) for item in include_types} if include_types is not None else None
    exclude_type_set = {str(item) for item in exclude_types} if exclude_types is not None else None

    selected: list[Tool | dict[str, Any]] = []
    for tool in tool_items:
        tool_name = get_toolbox_tool_name(tool)
        tool_type = get_toolbox_tool_type(tool)

        if include_name_set is not None and tool_name not in include_name_set:
            continue
        if exclude_name_set is not None and tool_name in exclude_name_set:
            continue
        if include_type_set is not None and tool_type not in include_type_set:
            continue
        if exclude_type_set is not None and tool_type in exclude_type_set:
            continue
        if predicate is not None and not predicate(tool):
            continue

        selected.append(tool)

    return selected


@experimental(feature_id=ExperimentalFeature.TOOLBOXES)
def sanitize_foundry_response_tool(tool_item: Any) -> Any:
    """Return a Responses-API-safe tool payload for Foundry hosted tools.

    Azure AI Projects toolbox reads can currently return hosted tool objects with
    extra read-model decoration fields such as top-level ``name`` and
    ``description``. Azure AI Foundry rejects at least ``name`` on Responses API
    requests with:

    ``Unknown parameter: 'tools[0].name'``.

    We defensively strip these decoration fields for non-function hosted tools so
    the round-trip
    ``toolbox.tools -> Agent(..., tools=...) -> run()`` works, while the Azure
    SDK/service behavior is corrected upstream.
    """
    if isinstance(tool_item, FoundryMCPTool):
        sanitized: dict[str, Any] = dict(cast("Mapping[str, Any]", tool_item))
        sanitized.pop("name", None)
        sanitized.pop("description", None)
        return sanitized

    if isinstance(tool_item, Mapping):
        mapping = cast("Mapping[str, Any]", tool_item)
        if "type" in mapping and mapping.get("type") not in {"function", "custom"}:
            sanitized = dict(mapping)
            sanitized.pop("name", None)
            sanitized.pop("description", None)
            return sanitized

    return cast(Any, tool_item)
