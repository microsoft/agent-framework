# Copyright (c) Microsoft. All rights reserved.

"""
MCP Long-Running Task (SEP-2663) Example

Demonstrates that ``MCPStdioTool`` transparently drives the MCP long-running
task lifecycle for tools that advertise ``execution.taskSupport == "required"``.
The agent observes a single function-call result; the framework handles the
``tools/call`` → ``tasks/get`` (polled) → ``tasks/result`` sequence in the
background.

Run it as a single file. The script doubles as both the client and the stdio
MCP child server (the child branch is selected via ``--server``):

    python mcp_long_running_task.py

Requirements:
- Azure CLI sign-in (``az login``) — used for Entra-ID auth against Azure OpenAI.
- ``AZURE_OPENAI_ENDPOINT`` — your Azure OpenAI resource endpoint, e.g.
  ``https://<resource>.openai.azure.com/``.
- ``AZURE_OPENAI_CHAT_MODEL`` (or ``AZURE_OPENAI_MODEL``) — the deployment name,
  e.g. ``gpt-4o-mini``.

This sample uses the lower-level ``mcp.server.lowlevel.Server`` so it can:
1. Advertise a tool with ``execution=ToolExecution(taskSupport="required")``.
2. Enable the SDK's experimental task support for the ``tasks/*`` lifecycle.
"""

import asyncio
import sys
from datetime import timedelta
from typing import Any

from agent_framework import Agent, MCPStdioTool, MCPTaskOptions
from agent_framework.openai import OpenAIChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# MCP stdio server (child-process branch)
# ---------------------------------------------------------------------------


async def _run_server() -> None:
    """Run a minimal stdio MCP server exposing one long-running tool."""
    import mcp.types as types
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server

    server: Server[Any, Any] = Server("mcp-long-running-task-demo")
    # Auto-registers handlers for tasks/get, tasks/result, tasks/cancel, tasks/list
    # backed by an in-memory store.
    server.experimental.enable_tasks()

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:  # pyright: ignore[reportUnusedFunction]
        return [
            types.Tool(
                name="slow_summary",
                description=(
                    "Produces a short summary of the supplied text after simulating several seconds of expensive work."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to summarize.",
                        }
                    },
                    "required": ["text"],
                },
                # Advertise that this tool MUST be invoked via the task lifecycle.
                execution=types.ToolExecution(taskSupport="required"),
            )
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> Any:  # pyright: ignore[reportUnusedFunction]
        if name != "slow_summary":
            raise ValueError(f"Unknown tool: {name}")

        ctx = server.request_context

        async def _work(task: Any) -> types.CallToolResult:
            await task.update_status("Thinking...")
            await asyncio.sleep(15.0)
            text: str = (arguments.get("text") or "").strip()
            words = text.split()
            preview = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
            summary = (
                f"Summarized {len(words)} word(s). First few words: '{preview}'."
                if words
                else "No input text was provided."
            )
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=summary)],
                isError=False,
            )

        if not ctx.experimental.is_task:
            # Client invoked the tool without task augmentation. Return a hard
            # error so a misconfigured client surfaces the problem clearly.
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text="'slow_summary' must be invoked as a task.",
                    )
                ],
                isError=True,
            )

        return await ctx.experimental.run_task(_work)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# ---------------------------------------------------------------------------
# Agent client (default branch)
# ---------------------------------------------------------------------------


async def _run_client() -> None:
    mcp_tool = MCPStdioTool(
        name="LongRunningDemo",
        description="Demo MCP server exposing a tool that advertises taskSupport=required.",
        command=sys.executable,
        args=[__file__, "--server"],
        # Optional: cap individual tasks at two minutes. The server may apply its
        # own default if this is omitted.
        task_options=MCPTaskOptions(default_ttl=timedelta(minutes=2)),
    )

    async with Agent(
        client=OpenAIChatClient(credential=AzureCliCredential()),
        name="LROAgent",
        instructions=(
            "You are a helpful assistant. Use the slow_summary tool when the user "
            "asks for a summary. Wait for the result and present it directly."
        ),
        tools=mcp_tool,
    ) as agent:
        prompt = (
            "Please summarize the following text using your slow_summary tool: "
            "'The Model Context Protocol lets language models talk to external "
            "tools and resources through a small JSON-RPC surface.'"
        )

        print("=== run() ===")
        print(f"User: {prompt}")
        response = await agent.run(prompt)
        print(f"Agent: {response.text}\n")

        print("=== run(stream=True) ===")
        print(f"User: {prompt}")
        print("Agent: ", end="", flush=True)
        async for update in agent.run(prompt, stream=True):
            if update.text:
                print(update.text, end="", flush=True)
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        asyncio.run(_run_server())
        return
    asyncio.run(_run_client())


if __name__ == "__main__":
    main()
