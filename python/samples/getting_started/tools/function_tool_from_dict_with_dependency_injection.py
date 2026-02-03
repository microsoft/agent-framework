# Copyright (c) Microsoft. All rights reserved.
# type: ignore
"""
Local Tool with Dependency Injection Example

This example demonstrates how to create a FunctionTool using the agent framework's
dependency injection system. Instead of providing the function at initialization time,
the actual callable function is injected during deserialization from a dictionary definition.

Note:
    The serialization and deserialization feature used in this example is currently
    in active development. The API may change in future versions as we continue
    to improve and extend its functionality. Please refer to the latest documentation
    for any updates to the dependency injection patterns.

Usage:
    Run this script to see how a FunctionTool can be created from a dictionary
    definition with the function injected at runtime. The agent will use this tool
    to perform arithmetic operations.
"""

import asyncio

from agent_framework import FunctionTool
from agent_framework.openai import OpenAIResponsesClient

definition = {
    "type": "function_tool",
    "name": "add_numbers",
    "description": "Add two numbers together.",
    "input_model": {
        "properties": {
            "a": {"description": "The first number", "type": "integer"},
            "b": {"description": "The second number", "type": "integer"},
        },
        "required": ["a", "b"],
        "title": "func_input",
        "type": "object",
    },
}


async def main() -> None:
    """Main function demonstrating creating a tool with an injected function."""

    def func(a, b) -> int:
        """Add two numbers together."""
        return a + b

    # Create the FunctionTool using dependency injection
    # The 'definition' dictionary contains the serialized tool configuration,
    # while the actual function implementation is provided via dependencies.
    #
    # Dependency structure: {"function_tool": {"name:add_numbers": {"func": func}}}
    # - "function_tool": matches the tool type identifier
    # - "name:add_numbers": instance-specific injection targeting tools with name="add_numbers"
    # - "func": the parameter name that will receive the injected function
    tool = FunctionTool.from_dict(definition, dependencies={"function_tool": {"name:add_numbers": {"func": func}}})

    agent = OpenAIResponsesClient().as_agent(
        name="FunctionToolAgent", instructions="You are a helpful assistant.", tools=tool
    )
    response = await agent.run("What is 5 + 3?")
    print(f"Response: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
