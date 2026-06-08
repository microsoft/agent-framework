# Copyright (c) Microsoft. All rights reserved.

"""Dynamic CodeAct instructions and execute_code tool descriptions for Monty."""

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
            "Filesystem access is unavailable. OS-level paths raise `PermissionError`. "
            "If you need files, ask the agent operator to configure `workspace_root` or `file_mounts`."
        )

    lines = ["Filesystem access is enabled. Read and write paths via `pathlib.Path(...)` (or `os.path`)."]
    lines.append("Configured mounts:")
    for mount in mounts:
        cap = ""
        if mount.write_bytes_limit is not None:
            cap = f", write cap {mount.write_bytes_limit} bytes"
        lines.append(f"- `{mount.mount_path}` ({mount.mode}{cap})")

    writable = [mount for mount in mounts if mount.mode == "read-write"]
    if writable:
        writable_paths = ", ".join(f"`{m.mount_path}`" for m in writable)
        lines.append(
            f"Files written to {writable_paths} are returned to the caller as attached files; "
            "use these paths for any output artifacts."
        )

    return "\n".join(lines)


def build_codeact_instructions(
    *,
    tools: Sequence[FunctionTool],
    tools_visible_to_model: bool,
    mounts: Sequence[FileMount] = (),
) -> str:
    """Build dynamic CodeAct instructions for the effective Monty tool set."""
    tool_summaries = _format_tool_summaries(tools)
    filesystem_text = _format_filesystem_capabilities(mounts)

    usage_note = (
        "Some tools may also appear directly, but prefer `execute_code` whenever you need to combine "
        "Python control flow with sandbox tool calls."
        if tools_visible_to_model
        else "Provider-owned sandbox tools are not exposed separately; use `execute_code` when you need them."
    )

    return f"""You have one primary tool: `execute_code`.

Inside `execute_code`, call registered tools directly as async functions:
`result = await tool_name(param=value)`. Always use `await` and keyword arguments.
Your code is type-checked against the tool signatures below before execution.
`await call_tool('name', **kwargs)` is also supported as a fallback but is not type-checked.

For fan-out, use `asyncio.gather`:
`results = await asyncio.gather(tool_a(...), tool_b(...))`.

Surface results to the caller via `print(...)` (captured and returned as text)
or by ending the code with an expression whose value is JSON-encodable - the
value of the final expression is returned alongside captured stdout.

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

    return f"""Execute Python code in a Monty interpreter.

Inside the sandbox, call registered tools directly as typed async functions:
`result = await tool_name(param=value)`. Always use `await` and keyword arguments.
Code is type-checked against tool signatures before execution.
`await call_tool('name', **kwargs)` is also supported as a fallback.

For fan-out, use `asyncio.gather`:
`results = await asyncio.gather(tool_a(...), tool_b(...))`.

Filesystem capabilities:
{filesystem_text}

Registered tools:
{tool_summaries}

Surface results via `print(...)` (captured and returned as text) or by ending
with an expression whose value is JSON-encodable.
"""
