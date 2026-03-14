# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import FunctionInvocationContext, tool
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
AI Function with kwargs Example

This example demonstrates how to inject runtime context into an AI function
from the agent's run method, without exposing it to the AI model.

This is useful for passing runtime information like access tokens, user IDs, or
request-specific context that the tool needs but the model shouldn't know about
or provide. The injected context parameter can be typed as
``FunctionInvocationContext`` as shown here, or left untyped as ``ctx`` when you
prefer a lighter-weight sample setup.
"""


# Define the function tool with explicit invocation context.
# The context parameter can also be declared as an untyped ``ctx`` parameter.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
    ctx: FunctionInvocationContext,
) -> str:
    """Get the weather for a given location."""
    # Extract the injected argument from the explicit context
    user_id = ctx.kwargs.get("user_id", "unknown")

    # Simulate using the user_id for logging or personalization
    print(f"Getting weather for user: {user_id}")

    return f"The weather in {location} is cloudy with a high of 15°C."


async def main() -> None:
    agent = OpenAIResponsesClient().as_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather assistant.",
        tools=[get_weather],
    )

    # Pass the runtime context explicitly when running the agent.
    response = await agent.run(
        "What is the weather like in Amsterdam?",
        function_invocation_kwargs={"user_id": "user_123"},
    )

    print(f"Agent: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
