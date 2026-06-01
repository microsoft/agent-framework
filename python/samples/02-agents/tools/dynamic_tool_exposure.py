# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import Agent, FunctionInvocationContext, tool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Dynamic Tool Exposure (Progressive Tool Loading) Example

This example demonstrates "progressive tool exposure": a tool that adds more tools to
the agent at runtime, in the same run, via ``FunctionInvocationContext``.

Frontloading a model with hundreds of tools hurts tool-selection accuracy, bloats
context, and raises cost. Instead, you can start with a small set of "loader" tools and
let the model pull in additional tools on demand. Tools added with ``ctx.add_tools(...)``
(or removed with ``ctx.remove_tools(...)``) become available to the model on the next
iteration of the function-calling loop.
"""


# These math tools are not registered on the agent up front. They are added on demand by
# the ``load_math_tools`` tool below, and only then become callable by the model.
@tool(approval_mode="never_require")
def factorial(n: Annotated[int, Field(description="A non-negative integer.")]) -> str:
    """Compute the factorial of n."""
    if n < 0:
        return "Error: n must be a non-negative integer."
    result = 1
    for value in range(2, n + 1):
        result *= value
    return f"{n}! = {result}"


@tool(approval_mode="never_require")
def fibonacci(n: Annotated[int, Field(description="The 0-based index in the Fibonacci sequence.")]) -> str:
    """Compute the n-th Fibonacci number."""
    if n < 0:
        return "Error: n must be a non-negative integer."
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return f"fib({n}) = {a}"


# The only tool the agent starts with. When called, it exposes the math tools above so the
# model can use them on the next turn. Note the ``ctx`` parameter is injected by the
# framework and is not visible to the model.
@tool(approval_mode="never_require")
def load_math_tools(ctx: FunctionInvocationContext) -> str:
    """Load additional math tools (factorial, fibonacci) so they can be used."""
    ctx.add_tools([factorial, fibonacci])
    return "Loaded math tools: factorial, fibonacci. You can now call them."


async def main() -> None:
    agent = Agent(
        client=OpenAIChatClient(),
        name="MathAgent",
        instructions=(
            "You are a math assistant. If you need math capabilities that are not yet "
            "available, call load_math_tools first, then use the newly available tools."
        ),
        tools=[load_math_tools],
    )

    # The agent starts with only ``load_math_tools``. To answer the question it must first
    # load the math tools, then call ``factorial`` on the next iteration.
    print(f"Agent: {await agent.run('What is 5 factorial?')}")


if __name__ == "__main__":
    asyncio.run(main())
