# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Sequence

from agent_framework import FunctionTool

from ._types import FilesystemMode, NetworkMode


def _format_tool_summaries(tools: Sequence[FunctionTool]) -> str:
    if not tools:
        return "- No tools are currently registered inside the sandbox."

    lines: list[str] = []
    for tool_obj in tools:
        parameters = tool_obj.parameters().get("properties", {})
        parameter_names = [name for name in parameters if isinstance(name, str)]
        parameter_summary = ", ".join(parameter_names) if parameter_names else "none"
        description = str(tool_obj.description or "").strip() or "No description provided."
        lines.append(f"- `{tool_obj.name}`: {description} Parameters: {parameter_summary}.")
    return "\n".join(lines)


def _format_filesystem_capabilities(
    *,
    filesystem_mode: FilesystemMode,
    workspace_enabled: bool,
    mounted_paths: Sequence[str],
) -> str:
    if filesystem_mode == "none":
        return "Filesystem access is disabled."

    lines = ["Filesystem access is enabled."]
    lines.append("Read files from `/input`.")
    if filesystem_mode == "read_write":
        lines.append("Write generated artifacts to `/output`; returned files will be attached to the tool result.")
    else:
        lines.append("The sandbox does not expose a writable `/output` directory in this configuration.")

    if workspace_enabled:
        lines.append("The configured workspace root is available under `/input/`.")

    if mounted_paths:
        lines.append("Additional mounted paths:")
        lines.extend(f"- `{mounted_path}`" for mounted_path in mounted_paths)
    elif not workspace_enabled:
        lines.append("No workspace root or explicit file mounts are currently configured.")

    return "\n".join(lines)


def _format_network_capabilities(
    *,
    network_mode: NetworkMode,
    allowed_domains: Sequence[str],
    allowed_http_methods: Sequence[str],
) -> str:
    if network_mode == "none":
        return "Outbound network access is disabled."

    methods_text = ", ".join(allowed_http_methods) if allowed_http_methods else "all methods allowed by the backend"
    if not allowed_domains:
        return "Outbound network access uses an allow-list, but no domains are currently configured."

    lines = [
        "Outbound network access uses an allow-list.",
        f"Allowed HTTP methods: {methods_text}.",
        "Allowed domains:",
    ]
    lines.extend(f"- `{domain}`" for domain in allowed_domains)
    return "\n".join(lines)


def build_codeact_instructions(
    *,
    tools: Sequence[FunctionTool],
    tools_visible_to_model: bool,
    filesystem_mode: FilesystemMode,
    workspace_enabled: bool,
    mounted_paths: Sequence[str],
    network_mode: NetworkMode,
    allowed_domains: Sequence[str],
    allowed_http_methods: Sequence[str],
) -> str:
    """Build dynamic CodeAct instructions for the effective sandbox state."""
    usage_note = (
        "Some tools may also appear directly, but prefer `execute_code` whenever you need to combine Python "
        "control flow with sandbox tool calls."
        if tools_visible_to_model
        else "Provider-owned sandbox tools are not exposed separately; use `execute_code` when you need them."
    )

    return f"""You have one primary tool: execute_code.

Prefer one execute_code call per request when possible.
Its tool description contains the current `call_tool(...)` guidance, sandbox
tool registry, and capability limits.

{usage_note}
"""


def build_execute_code_description(
    *,
    tools: Sequence[FunctionTool],
    filesystem_mode: FilesystemMode,
    workspace_enabled: bool,
    mounted_paths: Sequence[str],
    network_mode: NetworkMode,
    allowed_domains: Sequence[str],
    allowed_http_methods: Sequence[str],
) -> str:
    """Build the dynamic execute_code tool description for standalone usage."""
    filesystem_text = _format_filesystem_capabilities(
        filesystem_mode=filesystem_mode,
        workspace_enabled=workspace_enabled,
        mounted_paths=mounted_paths,
    )
    network_text = _format_network_capabilities(
        network_mode=network_mode,
        allowed_domains=allowed_domains,
        allowed_http_methods=allowed_http_methods,
    )

    return f"""Execute Python in an isolated Hyperlight sandbox.

Inside the sandbox, `call_tool(name, **kwargs)` is available as a built-in for
registered host callbacks. Use the tool name as the first argument and keyword
arguments only. Do not pass a dict or any other positional arguments after the
tool name.

Registered sandbox tools:
{_format_tool_summaries(tools)}

Filesystem capabilities:
{filesystem_text}

Network capabilities:
{network_text}

Prefer `execute_code` when you need to combine one or more `call_tool(...)`
calls with Python control flow, loops, or post-processing.
"""
