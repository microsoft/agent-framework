# Copyright (c) Microsoft. All rights reserved.

"""
Dynamic Tool Loading Example

This sample demonstrates how tools can dynamically add new tools during execution,
which become immediately available for the same agent run. This is useful when:
- A tool needs to load additional capabilities based on context
- Tools need to be registered based on the result of a previous tool call
- Lazy loading of tools is needed for performance

The key is using **kwargs to receive the tools list from the framework.
"""

import asyncio
import logging
import os
from typing import Annotated, Any

from dotenv import load_dotenv

from agent_framework import ChatAgent, ai_function
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

@ai_function
def load_math_tools(
    operation: Annotated[str, "The math operation category to load (e.g., 'advanced')"],
    **kwargs: Any,
) -> str:
    """Load additional math tools dynamically based on the requested category.

    This tool demonstrates dynamic tool loading - it can add new tools to the
    agent during execution, making them available for immediate use.
    """
    # Access tools list directly
    tools_list = kwargs.get("tools")

    if not tools_list:
        return "Error: Cannot access tools list for dynamic tool loading"

    if operation == "advanced":
        # Define advanced math tools that will be added dynamically
        @ai_function
        def calculate_factorial(n: Annotated[int, "The number to calculate factorial for"]) -> str:
            """Calculate the factorial of a number."""
            if n < 0:
                return "Error: Factorial is not defined for negative numbers"
            result = 1
            for i in range(1, n + 1):
                result *= i
            return f"The factorial of {n} is {result}"

        @ai_function
        def calculate_fibonacci(n: Annotated[int, "The position in Fibonacci sequence"]) -> str:
            """Calculate the nth Fibonacci number."""
            if n <= 0:
                return "Error: Position must be positive"
            if n == 1 or n == 2:
                return f"The {n}th Fibonacci number is 1"
            a, b = 1, 1
            for _ in range(n - 2):
                a, b = b, a + b
            return f"The {n}th Fibonacci number is {b}"

        # Add the new tools to the tools list
        if isinstance(tools_list, list):
            tools_list.extend([calculate_factorial, calculate_fibonacci])
            return "Successfully loaded advanced math tools: factorial and fibonacci"
        return "Error: Tools list is not a list"

    return f"Unknown operation category: {operation}"


@ai_function
def add(x: Annotated[int, "First number"], y: Annotated[int, "Second number"]) -> str:
    """Add two numbers together."""
    return f"{x} + {y} = {x + y}"


async def main() -> None:
    # Create a chat client and agent with the dynamic tool loader and a basic tool
    client = AzureOpenAIChatClient(credential=AzureCliCredential())
    agent = ChatAgent(
        chat_client=client,
        instructions=(
            "You are a helpful math assistant. "
            "You have access to basic math operations and can load additional tools as needed. "
            "When you need advanced math operations like factorial or fibonacci, "
            "first use load_math_tools to load them, then use the newly loaded tools."
        ),
        name="MathAgent",
        tools=[add, load_math_tools],
    )   

    print("=" * 80)
    print("Using basic tools and dynamically loading and using advanced tools")
    print("=" * 80)
    print("Query: Calculate sum of 5 and 29 and the factorial of 5 and the 10th Fibonacci number")
    print("\nExpected behavior:")
    print("1. Agent realizes it needs advanced math tools")
    print("2. Agent calls load_math_tools('advanced') to add factorial and fibonacci")
    print("3. Agent uses the newly loaded tools in the same run")
    print("-" * 80)

    response = await agent.run("Calculate sum of 5 and 29 and the factorial of 5 and the 10th Fibonacci number")
    print(f"Response: {response.text}\n")

"""
Expected Output:
================================================================================
Using basic tools and dynamically loading and using advanced tools
================================================================================
Query: Calculate sum of 5 and 29 and the factorial of 5 and the 10th Fibonacci number

Expected behavior:
1. Agent uses basic tools to calculate sum of 5 and 29
2. Agent realizes it needs advanced math tools for factorial and fibonacci
2. Agent calls load_math_tools('advanced') to add factorial and fibonacci
3. Agent uses the newly loaded tools in the same run
--------------------------------------------------------------------------------
Response: Sum of 5 and 29 is 34, the factorial of 5 is 120 and the 10th Fibonacci number is 55
"""

if __name__ == "__main__":
    asyncio.run(main())
