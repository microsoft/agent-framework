# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio

from agent_framework import AIFunction
from agent_framework.openai import OpenAIResponsesClient

definition = {
    "type": "ai_function",
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

    # Create the tool with the injected function
    # a side benefit is that I can now have untyped functions
    tool = AIFunction.from_dict(definition, dependencies={"ai_function": {"name:add_numbers": {"func": func}}})

    agent = OpenAIResponsesClient().create_agent(
        name="FunctionToolAgent", instructions="You are a helpful assistant.", tools=tool
    )
    response = await agent.run("What is 5 + 3?")
    print(f"Response: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
