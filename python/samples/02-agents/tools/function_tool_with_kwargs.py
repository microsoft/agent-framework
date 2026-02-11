# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated, Any

from agent_framework import tool
from agent_framework.openai import OpenAIResponsesClient
from pydantic import Field

"""
AI Function with kwargs Example

This example demonstrates how to inject custom keyword arguments (kwargs) into an AI function
from the agent's run method, without exposing them to the AI model.

This is useful for passing runtime information like access tokens, user IDs, or
request-specific context that the tool needs but the model shouldn't know about
or provide.
"""


# Define the function tool with **kwargs to accept injected arguments
# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
    **kwargs: Any,
) -> str:
    """Get the weather for a given location."""
    # Extract the injected argument from kwargs
    user_id = kwargs.get("user_id", "unknown")

    # Simulate using the user_id for logging or personalization
    print(f"Getting weather for user: {user_id}")

    return f"The weather in {location} is cloudy with a high of 15°C."


async def main() -> None:
    agent = OpenAIResponsesClient().as_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather assistant.",
        tools=[get_weather],
    )

    # Pass the injected argument when running the agent
    # The 'user_id' kwarg will be passed down to the tool execution via **kwargs
    response = await agent.run("What is the weather like in Amsterdam?", user_id="user_123")

    print(f"Agent: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
