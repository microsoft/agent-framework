# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Sequence

from agent_framework import FunctionTool

from ._types import AllowedDomain


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
    filesystem_enabled: bool,
    workspace_enabled: bool,
    mounted_paths: Sequence[str],
) -> str:
    if not filesystem_enabled:
        return "Filesystem access is unavailable because no workspace root or file mounts are configured."

    lines = ["Filesystem access is enabled."]
    lines.append("Read files from `/input`.")
    lines.append("Write generated artifacts to `/output`; returned files will be attached to the tool result.")

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
    allowed_domains: Sequence[AllowedDomain],
) -> str:
    if not allowed_domains:
        return "Outbound network access is unavailable because no allow-listed targets are configured."

    lines = ["Outbound network access is allowed only for these configured targets:"]
    for allowed_domain in allowed_domains:
        methods_text = (
            ", ".join(allowed_domain.methods) if allowed_domain.methods else "all methods allowed by the backend"
        )
        lines.append(f"- `{allowed_domain.target}`: {methods_text}.")
    return "\n".join(lines)


def build_codeact_instructions(
    *,
    tools: Sequence[FunctionTool],
    tools_visible_to_model: bool,
    filesystem_enabled: bool = False,
) -> str:
    """Build dynamic CodeAct instructions for the effective sandbox state."""
    usage_note = (
        "Some tools may also appear directly, but prefer `execute_code` whenever you need to combine Python "
        "control flow with sandbox tool calls."
        if tools_visible_to_model
        else "Provider-owned sandbox tools are not exposed separately; use `execute_code` when you need them."
    )

    output_note = (
        "To surface results from `execute_code`, end the code with `print(...)`; the sandbox does not "
        "return the value of the last expression."
    )
    if filesystem_enabled:
        output_note += (
            " For larger artifacts, write them to `/output/<filename>` instead — returned files will be "
            "attached to the tool result."
        )

    return f"""You have one primary tool: execute_code.

Prefer one execute_code call per request when possible.
Its tool description contains the current `call_tool(...)` guidance, sandbox
tool registry, and capability limits.

{output_note}

{usage_note}
"""


def build_execute_code_description(
    *,
    tools: Sequence[FunctionTool],
    filesystem_enabled: bool,
    workspace_enabled: bool,
    mounted_paths: Sequence[str],
    allowed_domains: Sequence[AllowedDomain],
) -> str:
    """Build the dynamic execute_code tool description for standalone usage."""
    filesystem_text = _format_filesystem_capabilities(
        filesystem_enabled=filesystem_enabled,
        workspace_enabled=workspace_enabled,
        mounted_paths=mounted_paths,
    )
    network_text = _format_network_capabilities(
        allowed_domains=allowed_domains,
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
