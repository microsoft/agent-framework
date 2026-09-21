# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

server = FastMCP(name="typesafe-weather-sample")


@server.tool(name="get_weather", description="Get weather for Seattle or Paris.")
def get_weather(city: Literal["Seattle", "Paris"], detailed: bool) -> str:
    """Return deterministic sample weather."""
    suffix = " with a detailed hourly forecast" if detailed else ""
    return f"{city} is sunny and 22 C{suffix}."


if __name__ == "__main__":
    server.run(transport="stdio")
