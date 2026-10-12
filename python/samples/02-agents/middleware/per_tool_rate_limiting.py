# Copyright (c) Microsoft. All rights reserved.

"""Demonstrate per-tool request-rate limiting without external services."""

import asyncio

from agent_framework import (
    FunctionInvocationContext,
    ToolRateLimit,
    ToolRateLimitMiddleware,
    tool,
)


@tool
def search() -> str:
    """Search for information."""
    return "Search completed"


@tool
def lookup() -> str:
    """Look up a record."""
    return "Lookup completed"


async def main() -> None:
    """Demonstrate independent quotas and fail-fast rejection."""
    limiter = ToolRateLimitMiddleware({
        "search": ToolRateLimit(requests_per_second=1, burst=2),
        "lookup": ToolRateLimit(requests_per_second=1, burst=1),
    })

    async def run_tool(function) -> None:
        context = FunctionInvocationContext(
            function=function,
            arguments={},
        )

        async def execute() -> None:
            context.result = function.func()

        await limiter.process(context, execute)
        print(f"{function.name}: {context.result}")

    print("Search: burst capacity of 2")
    for _ in range(3):
        await run_tool(search)

    print("\nLookup: independent burst capacity of 1")
    for _ in range(2):
        await run_tool(lookup)


if __name__ == "__main__":
    asyncio.run(main())
