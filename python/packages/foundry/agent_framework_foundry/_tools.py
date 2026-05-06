# Copyright (c) Microsoft. All rights reserved.

"""Shared tool helpers for Foundry chat clients.

Includes Responses-API payload sanitization for Foundry hosted tools.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from azure.ai.projects.models import MCPTool as FoundryMCPTool


def _validate_hosted_tool_payload(sanitized: Mapping[str, Any]) -> None:
    """Fail fast on hosted tool payloads that would always be rejected by the Responses API.

    These mismatches are not injectable defaults — the caller must supply the
    missing information — so surfacing a clear error here points at the toolbox
    definition instead of letting the API return a generic 400.
    """
    tool_type = sanitized.get("type")
    if tool_type == "file_search" and not sanitized.get("vector_store_ids"):
        raise ValueError(
            "'file_search' tool is missing required 'vector_store_ids'. "
            "Update the tool definition to include at least one vector store ID."
        )
    if tool_type == "mcp" and not sanitized.get("server_url") and not sanitized.get("project_connection_id"):
        raise ValueError(
            "'mcp' tool is missing both 'server_url' and 'project_connection_id'. "
            "Update the tool definition to include one of these."
        )


def _sanitize_foundry_response_tool(tool_item: Any) -> Any:  # pyright: ignore[reportUnusedFunction]
    """Return a Responses-API-safe tool payload for Foundry hosted tools.

    Reconciles known mismatches between hosted tool definitions and the Responses API:

    1. Hosted tool objects may carry read-model fields such as top-level ``name``
       and ``description``. The Responses API rejects at least ``name`` with
       ``Unknown parameter: 'tools[0].name'``. These fields are stripped from
       non-function hosted tool payloads.
    2. ``code_interpreter`` tools without a ``container`` field (the Azure SDK
       treats it as optional) are rejected by the Responses API with
       ``Missing required parameter: 'tools[N].container'``. A default
       ``{"type": "auto"}`` container is injected when absent.
    3. Hosted tools that are structurally incomplete in ways that cannot be
       defaulted (``file_search`` without ``vector_store_ids``, ``mcp`` without
       either ``server_url`` or ``project_connection_id``) raise ``ValueError``
       with a message that points at the tool definition.
    """
    if isinstance(tool_item, FoundryMCPTool):
        sanitized: dict[str, Any] = dict(cast("Mapping[str, Any]", tool_item))
        sanitized.pop("name", None)
        sanitized.pop("description", None)
        _validate_hosted_tool_payload(sanitized)
        return sanitized

    if isinstance(tool_item, Mapping):
        mapping = cast("Mapping[str, Any]", tool_item)
        if "type" in mapping and mapping.get("type") not in {"function", "custom"}:
            sanitized = dict(mapping)
            sanitized.pop("name", None)
            sanitized.pop("description", None)
            if sanitized.get("type") == "code_interpreter" and "container" not in sanitized:
                sanitized["container"] = {"type": "auto"}
            _validate_hosted_tool_payload(sanitized)
            return sanitized

    return cast(Any, tool_item)
