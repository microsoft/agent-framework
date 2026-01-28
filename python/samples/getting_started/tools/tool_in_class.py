# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import tool
from agent_framework.openai import OpenAIResponsesClient

"""
This sample demonstrates using tool within a class,
showing how to manage state within the class that affects tool behavior.

And how to use tool-decorated methods as tools in an agent in order to adjust the behavior of a tool.
"""


class MyFunctionClass:
    def __init__(self, safe: bool = False) -> None:
        """Simple class with two tools: divide and add.

        The safe parameter controls whether divide raises on division by zero or returns `infinity` for divide by zero.
        """
        self.safe = safe

    def divide(
        self,
        a: Annotated[int, "Numerator"],
        b: Annotated[int, "Denominator"],
    ) -> str:
        """Divide two numbers, safe to use also with 0 as denominator."""
        result = "∞" if b == 0 and self.safe else a / b
        return f"{a} / {b} = {result}"

    def add(
        self,
        x: Annotated[int, "First number"],
        y: Annotated[int, "Second number"],
    ) -> str:
        return f"{x} + {y} = {x + y}"


async def main():
    # Creating my function class with safe division enabled
    tools = MyFunctionClass(safe=True)
    # Applying the tool decorator to one of the methods of the class
    add_function = tool(description="Add two numbers.")(tools.add)

    agent = OpenAIResponsesClient().as_agent(
        name="ToolAgent",
        instructions="Use the provided tools.",
    )
    print("=" * 60)
    print("Step 1: Call divide(10, 0) - tool returns infinity")
    query = "Divide 10 by 0"
    response = await agent.run(
        query,
        tools=[add_function, tools.divide],
    )
    print(f"Response: {response.text}")
    print("=" * 60)
    print("Step 2: Call set safe to False and call again")
    # Disabling safe mode to allow exceptions
    tools.safe = False
    response = await agent.run(query, tools=[add_function, tools.divide])
    print(f"Response: {response.text}")
    print("=" * 60)


"""
Expected Output:
============================================================
Step 1: Call divide(10, 0) - tool returns infinity
Response: Division by zero is undefined in standard arithmetic. There is no real number that equals 10 divided by 0.

- If you look at limits: as x → 0+ (denominator approaches 0 from the positive side), 10/x → +∞; as x → 0−, 10/x → −∞.
- Some calculators may display "infinity" or give an error, but that's not a real number.

If you want a numeric surrogate, you can use a small nonzero denominator, e.g., 10/0.001 = 10000. Would you like to
see more on limits or handle it with a tiny epsilon?
============================================================
Step 2: Call set safe to False and call again
[2025-10-31 16:17:44 - /Users/edvan/Work/agent-framework/python/packages/core/agent_framework/_tools.py:718 - ERROR]
Function failed. Error: division by zero
Response: Division by zero is undefined in standard arithmetic. There is no number y such that 0 × y = 10.

If you’re looking at limits:
- as x → 0+, 10/x → +∞
- as x → 0−, 10/x → −∞
So the limit does not exist.

In programming, dividing by zero usually raises an error or results in special values (e.g., NaN or ∞) depending
on the language.

If you want, tell me what you’d like to do instead (e.g., compute 10 divided by 2, or handle division by zero safely
in code), and I can help with examples.
============================================================
"""

if __name__ == "__main__":
    asyncio.run(main())
