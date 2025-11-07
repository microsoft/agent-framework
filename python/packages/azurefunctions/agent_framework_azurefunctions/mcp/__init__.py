# Copyright (c) Microsoft. All rights reserved.

"""MCP (Model Context Protocol) Server Integration for Agent Framework.

This module provides the MCPServerExtension class to easily expose durable agents
as MCP tools, allowing them to be used by any MCP-compatible client (Claude Desktop,
Cursor, VSCode, etc.).

Example:
    ```python
    from agent_framework.azurefunctions import AgentFunctionApp
    from agent_framework.azurefunctions.mcp import MCPServerExtension

    app = AgentFunctionApp("MyApp")
    app.add_agent(weather_agent)

    # Enable MCP server - all agents become MCP tools
    mcp = MCPServerExtension(app)
    app.register_mcp_server(mcp)
    ```
"""

from ._extension import MCPServerExtension
from ._models import MCPCallResult, MCPResource, MCPTool

__all__ = [
    "MCPServerExtension",
    "MCPTool",
    "MCPResource",
    "MCPCallResult",
]
