# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-hosting-mcp",
#     "mcp>=1.27.0,<2",
#     "starlette>=0.40",
#     "uvicorn>=0.30",
# ]
# ///
# Run with: uv run workflow_app.py

# Copyright (c) Microsoft. All rights reserved.

"""Host a typed Agent Framework workflow through native MCP constructs.

``MCPWorkflowTool`` derives the MCP arguments from the start executor's input
type. This sample uses a dataclass, so its fields become the tool's top-level
arguments. The application still owns the MCP server and transport.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import uvicorn
from agent_framework import WorkflowBuilder, WorkflowContext, executor
from agent_framework_hosting import WorkflowState
from agent_framework_hosting_mcp import MCPWorkflowTool
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount


@dataclass
class DraftRequest:
    """Input contract exposed by the MCP tool."""

    topic: str
    audience: str
    paragraph_count: int = 2


def create_workflow():
    """Create an independent workflow instance for one MCP call."""

    @executor(id="draft")
    async def draft(request: DraftRequest, ctx: WorkflowContext[object, str]) -> None:
        paragraphs = "\n\n".join(
            f"Paragraph {index + 1}: {request.topic} for {request.audience}."
            for index in range(request.paragraph_count)
        )
        await ctx.yield_output(paragraphs)

    return WorkflowBuilder(
        start_executor=draft,
        name="Draft Workflow",
        description="Draft short content for a specified topic and audience.",
        output_from=[draft],
    ).build()


server = Server("agent-framework-hosting-mcp-workflow-sample")
workflow_tool = MCPWorkflowTool(
    WorkflowState(create_workflow, cache_target=False),
    name="draft_content",
)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the workflow-derived MCP tool definition."""
    return await workflow_tool.list_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, object] | None) -> list[types.ContentBlock]:
    """Run a fresh workflow instance with validated MCP arguments."""
    return await workflow_tool.call_tool(name, arguments)


session_manager = StreamableHTTPSessionManager(
    app=server,
    event_store=None,
    json_response=True,
    stateless=True,
)


@asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncIterator[None]:
    """Start and stop the native MCP transport."""
    async with session_manager.run():
        yield


app = Starlette(
    routes=[Mount("/", app=session_manager.handle_request)],
    lifespan=lifespan,
)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
