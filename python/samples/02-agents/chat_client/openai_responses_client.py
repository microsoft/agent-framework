# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import tool
from agent_framework.openai import OpenAIResponsesClient
from pydantic import Field

"""
OpenAI Responses Client Direct Usage Example

Demonstrates direct OpenAIResponsesClient usage for structured response generation with OpenAI models.
Shows function calling capabilities with custom business logic.

"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    client = OpenAIResponsesClient()
    message = "What's the weather in Amsterdam and in Paris?"
    stream = True
    print(f"User: {message}")
    print("Assistant: ", end="")
    response = client.get_response(message, stream=stream, options={"tools": get_weather})
    if stream:
        # TODO: review names of the methods, could be related to things like HTTP clients?
        response.with_transform_hook(lambda chunk: print(chunk.text, end=""))
        await response.get_final_response()
    else:
        response = await response
        print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())
