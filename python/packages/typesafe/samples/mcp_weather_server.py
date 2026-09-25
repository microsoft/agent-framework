# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp>=1.27.0,<2",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

"""
Local stdio MCP server used by mcp_function_calling.py.

The MCP tool schema contains only a Literal and a boolean, both supported by the
TypeSafe function-calling adapter. This process communicates through MCP stdio;
run mcp_function_calling.py for user-facing output.
"""

# 1. Define a small deterministic MCP server and one compatible closed-set tool.
server = FastMCP(name="typesafe-weather-sample")


@server.tool(name="get_weather", description="Get weather for Seattle or Paris.")
def get_weather(city: Literal["Seattle", "Paris"], detailed: bool) -> str:
    """Return deterministic sample weather."""
    suffix = " with a detailed hourly forecast" if detailed else ""
    return f"{city} is sunny and 22 C{suffix}."


if __name__ == "__main__":
    server.run(transport="stdio")


"""
Expected behavior:

This server waits for MCP protocol requests on stdio and does not print a
user-facing answer. When launched by mcp_function_calling.py, the client sample
prints:

Paris is sunny and 22 C with a detailed hourly forecast.
Success probability: 0.950
"""
