# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys
from typing import Any

from agent_framework import Agent, MCPStdioTool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

"""
MCP Progressive Disclosure Example

This sample demonstrates how to connect an agent to a large MCP server without
frontloading every remote tool schema into the model prompt.

The sample starts a tiny local MCP stdio server in a child process. The server
advertises three tools:

1. ``get_server_status`` — always visible to the model.
2. ``search_docs`` — allowed, but hidden until the model calls ``docs_load_tool``.
3. ``internal_admin_report`` — not listed in ``allowed_tools``, so the model never
   sees it in ``docs_list_mcp_tools`` and cannot load it.

The ``MCPStdioTool`` is configured with:

1. ``use_progressive_disclosure=True`` to enable loader tools.
2. ``always_load=["get_server_status"]`` to keep one cheap tool visible up front.
3. ``allowed_tools=[...]`` to define the only remote tools the model may discover
   or load.
4. ``tool_name_prefix="docs"`` so multiple MCP servers can expose their own
   ``docs_list_mcp_tools`` / ``docs_load_tool`` names without collisions.

Sample output:
User: Explain how progressive MCP tool disclosure works. First inspect the MCP
tools you can load, then load the docs search tool, then use it.
Agent: Progressive disclosure starts with a small set of tools. I listed the
available MCP tools, loaded docs_search_docs, and used it to find that hidden
MCP tools become available on the next function-calling iteration.
"""


load_dotenv()


async def _run_server() -> None:
    """Run a minimal stdio MCP server with visible, loadable, and filtered tools."""
    import mcp.types as types
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server

    server: Server[Any, Any] = Server("mcp-progressive-disclosure-demo")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:  # pyright: ignore[reportUnusedFunction]
        return [
            types.Tool(
                name="get_server_status",
                description="Return the health of the demo MCP server.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="search_docs",
                description="Search short documentation snippets about MCP progressive disclosure.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The documentation search query.",
                        }
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="internal_admin_report",
                description="Internal server details that are intentionally filtered out by allowed_tools.",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:  # pyright: ignore[reportUnusedFunction]
        if name == "get_server_status":
            text = "The demo MCP server is healthy. Use search_docs for progressive disclosure details."
        elif name == "search_docs":
            query = str(arguments.get("query", "")).strip() or "progressive disclosure"
            text = (
                f"Search results for '{query}': In progressive MCP disclosure, the agent starts with "
                "list/load tools and selected always-loaded tools. Calling load_tool adds an allowed "
                "remote MCP tool to the live tool list for the next model iteration."
            )
        elif name == "internal_admin_report":
            text = "This tool should not be discoverable because it is excluded by allowed_tools."
        else:
            text = f"Unknown tool: {name}"
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)])

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def _run_client() -> None:
    """Run an agent that progressively discovers and loads MCP tools."""
    # 1. Create the MCP tool. Only get_server_status is visible at first; search_docs
    #    is discoverable through docs_list_mcp_tools and loadable through docs_load_tool.
    mcp_tool = MCPStdioTool(
        name="DocsMCP",
        description="Demo MCP server with progressively loaded documentation tools.",
        command=sys.executable,
        args=[__file__, "--server"],
        allowed_tools=["get_server_status", "search_docs"],
        use_progressive_disclosure=True,
        always_load=["get_server_status"],
        tool_name_prefix="docs",
    )

    # 2. Create an agent with the progressive MCP tool.
    async with Agent(
        client=OpenAIChatClient(),
        name="ProgressiveMCPAgent",
        instructions=(
            "You are a helpful assistant. To answer documentation questions, first call "
            "docs_list_mcp_tools to see which MCP tools are available. If you need a "
            "hidden tool, call docs_load_tool with that tool's remote name, then call "
            "the newly available prefixed tool on the next iteration. Do not invent "
            "tools that are not listed."
        ),
        tools=mcp_tool,
    ) as agent:
        # 3. Ask a question that requires loading a hidden MCP tool.
        prompt = (
            "Explain how progressive MCP tool disclosure works. First inspect the MCP "
            "tools you can load, then load the docs search tool, then use it."
        )
        print(f"User: {prompt}")
        response = await agent.run(prompt)
        print(f"Agent: {response.text}")


async def main() -> None:
    """Run either the MCP server branch or the agent client branch."""
    if "--server" in sys.argv:
        await _run_server()
    else:
        await _run_client()


if __name__ == "__main__":
    asyncio.run(main())
