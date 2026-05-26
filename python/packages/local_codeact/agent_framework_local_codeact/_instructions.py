# Copyright (c) Microsoft. All rights reserved.

"""Dynamic CodeAct instructions and execute_code descriptions for local execution."""

from __future__ import annotations

from collections.abc import Sequence

from agent_framework import FunctionTool

from ._types import FileMount


def _format_tool_summaries(tools: Sequence[FunctionTool]) -> str:
    if not tools:
        return "- No tools are currently registered."

    lines: list[str] = []
    for tool_obj in tools:
        parameters = tool_obj.parameters().get("properties", {})
        parameter_names = [name for name in parameters if isinstance(name, str)]
        parameter_summary = ", ".join(parameter_names) if parameter_names else "none"
        description = str(tool_obj.description or "").strip() or "No description provided."
        lines.append(f"- `{tool_obj.name}`: {description} Parameters: {parameter_summary}.")
    return "\n".join(lines)


def _format_filesystem_capabilities(mounts: Sequence[FileMount]) -> str:
    if not mounts:
        return (
            "No workspace or file mounts are configured. Use only temporary files created by this execution, "
            "or ask the operator to configure a sandboxed workspace."
        )

    lines = [
        (
            "Configured directories are direct paths inside the surrounding sandbox. "
            "They are not virtualized by this package:"
        )
    ]
    for mount in mounts:
        cap = ""
        if mount.write_bytes_limit is not None:
            cap = f", capture cap {mount.write_bytes_limit} bytes"
        lines.append(f"- `{mount.mount_path}` -> `{mount.host_path}` ({mount.mode}{cap})")

    writable = [mount for mount in mounts if mount.mode == "read-write"]
    if writable:
        writable_paths = ", ".join(f"`{m.host_path}`" for m in writable)
        lines.append(
            f"New or modified files under {writable_paths} are returned to the caller as attached files. "
            "Use those paths for output artifacts."
        )

    return "\n".join(lines)


def build_codeact_instructions(
    *,
    tools: Sequence[FunctionTool],
    tools_visible_to_model: bool,
    mounts: Sequence[FileMount] = (),
) -> str:
    """Build dynamic CodeAct instructions for the effective local tool set."""
    tool_summaries = _format_tool_summaries(tools)
    filesystem_text = _format_filesystem_capabilities(mounts)

    usage_note = (
        "Some tools may also appear directly, but prefer `execute_code` whenever you need to combine "
        "Python control flow with host tool calls."
        if tools_visible_to_model
        else "Provider-owned host tools are not exposed separately; use `execute_code` when you need them."
    )

    return f"""You have one primary tool: `execute_code`.

`execute_code` runs Python locally in the agent environment. This is not a
security sandbox; rely on the surrounding Foundry/container/VM sandbox for
isolation.

Inside `execute_code`, call registered tools directly as async functions:
`result = await tool_name(param=value)`. Always use `await` and keyword arguments.
`await call_tool('name', **kwargs)` is also supported as a fallback.

For fan-out, use `asyncio.gather`:
`results = await asyncio.gather(tool_a(...), tool_b(...))`.

Surface results to the caller via `print(...)` (captured and returned as text)
or by ending the code with an expression whose value is JSON-encodable.

Filesystem capabilities:
{filesystem_text}

Registered tools:
{tool_summaries}

Prefer a single `execute_code` call per request when possible, combining
multiple tool calls with Python control flow.

{usage_note}
"""


def build_execute_code_description(
    *,
    tools: Sequence[FunctionTool],
    mounts: Sequence[FileMount] = (),
) -> str:
    """Build the dynamic ``execute_code`` tool description for standalone usage."""
    tool_summaries = _format_tool_summaries(tools)
    filesystem_text = _format_filesystem_capabilities(mounts)

    return f"""Execute Python code locally in the agent environment.

This is not a security sandbox. Use only when the surrounding environment
provides isolation, such as a Foundry hosted-agent sandbox.

Inside the code, call registered tools directly as async functions:
`result = await tool_name(param=value)`. Always use `await` and keyword arguments.
`await call_tool('name', **kwargs)` is also supported as a fallback.

Filesystem capabilities:
{filesystem_text}

Registered tools:
{tool_summaries}

Surface results via `print(...)` or by ending with a JSON-encodable expression.
"""
