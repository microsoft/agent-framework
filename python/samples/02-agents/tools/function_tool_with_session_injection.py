# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import AgentSession, FunctionInvocationContext, tool
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
AI Function with Session Injection Example

This example demonstrates explicitly passing an ``AgentSession`` through
``function_invocation_kwargs`` and reading it from ``FunctionInvocationContext.kwargs``.
The injected context parameter can be typed as ``FunctionInvocationContext`` as
shown here, or left untyped as ``ctx`` when you want the conventional untyped form.
"""


# Define the function tool with explicit invocation context.
# The context parameter can also be declared as an untyped parameter with the name: ``ctx``.
@tool(approval_mode="never_require")
async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
    ctx: FunctionInvocationContext,
) -> str:
    """Get the weather for a given location."""
    # FunctionInvocationContext does not surface agent sessions directly.
    # If a tool needs session data, pass it explicitly through function_invocation_kwargs.
    session = ctx.kwargs.get("session")
    if session and isinstance(session, AgentSession) and session.service_session_id:
        print(f"Session ID: {session.service_session_id}.")

    return f"The weather in {location} is cloudy."


async def main() -> None:
    agent = OpenAIResponsesClient().as_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather assistant.",
        tools=[get_weather],
        default_options={"store": True},
    )

    # Create a session
    session = agent.create_session()

    # Pass the session explicitly through function_invocation_kwargs when the tool needs it.
    print(
        f"Agent: {await agent.run('What is the weather in London?', session=session, function_invocation_kwargs={'session': session})}"
    )
    print(
        f"Agent: {await agent.run('What is the weather in Amsterdam?', session=session, function_invocation_kwargs={'session': session})}"
    )
    print(
        f"Agent: {await agent.run('What cities did I ask about?', session=session, function_invocation_kwargs={'session': session})}"
    )


if __name__ == "__main__":
    asyncio.run(main())
