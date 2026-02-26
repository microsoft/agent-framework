# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated, Any

from agent_framework import AgentSession, tool
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
AI Function with Session Injection Example

This example demonstrates the behavior when passing 'session' to agent.run()
and accessing that session in AI function.
"""


# Define the function tool with **kwargs
# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
    **kwargs: Any,
) -> str:
    """Get the weather for a given location."""
    # Get session object from kwargs
    session = kwargs.get("session")
    if session and isinstance(session, AgentSession) and session.service_session_id:
        print(f"Session ID: {session.service_session_id}.")

    return f"The weather in {location} is cloudy."


async def main() -> None:
    agent = OpenAIResponsesClient().as_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather assistant.",
        tools=[get_weather],
        options={"store": True},
    )

    # Create a session
    session = agent.create_session()

    # Run the agent with the session
    # Pass session via additional_function_arguments so tools can access it via **kwargs
    opts = {"additional_function_arguments": {"session": session}}
    print(f"Agent: {await agent.run('What is the weather in London?', session=session, options=opts)}")
    print(f"Agent: {await agent.run('What is the weather in Amsterdam?', session=session, options=opts)}")
    print(f"Agent: {await agent.run('What cities did I ask about?', session=session)}")


if __name__ == "__main__":
    asyncio.run(main())
