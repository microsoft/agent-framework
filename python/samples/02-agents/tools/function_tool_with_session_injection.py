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

This example demonstrates accessing the agent session inside a tool function
via ``FunctionInvocationContext.session``. The session is automatically
available when the agent is invoked with a session.
"""


# Define the function tool with explicit invocation context.
# The context parameter can also be declared as an untyped parameter with the name: ``ctx``.
@tool(approval_mode="never_require")
async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
    ctx: FunctionInvocationContext,
) -> str:
    """Get the weather for a given location."""
    session = ctx.session
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

    # Run the agent with the session; tools receive it via ctx.session.
    print(f"Agent: {await agent.run('What is the weather in London?', session=session)}")
    print(f"Agent: {await agent.run('What is the weather in Amsterdam?', session=session)}")
    print(f"Agent: {await agent.run('What cities did I ask about?', session=session)}")


if __name__ == "__main__":
    asyncio.run(main())
