# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated, Any

from agent_framework import AgentThread, tool
from agent_framework.openai import OpenAIChatClient
from pydantic import Field

"""
AI Function with Thread Injection Example

This example demonstrates the behavior when passing 'thread' to agent.run()
and accessing that thread in AI function.
"""


# Define the function tool with **kwargs
# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
    **kwargs: Any,
) -> str:
    """Get the weather for a given location."""
    # Get thread object from kwargs
    thread = kwargs.get("thread")
    if thread and isinstance(thread, AgentThread):
        if thread.message_store:
            messages = await thread.message_store.list_messages()
            print(f"Thread contains {len(messages)} messages.")
        elif thread.service_thread_id:
            print(f"Thread ID: {thread.service_thread_id}.")

    return f"The weather in {location} is cloudy."


async def main() -> None:
    agent = OpenAIChatClient().as_agent(
        name="WeatherAgent", instructions="You are a helpful weather assistant.", tools=[get_weather]
    )

    # Create a thread
    thread = agent.get_new_thread()

    # Run the agent with the thread
    print(f"Agent: {await agent.run('What is the weather in London?', thread=thread)}")
    print(f"Agent: {await agent.run('What is the weather in Amsterdam?', thread=thread)}")
    print(f"Agent: {await agent.run('What cities did I ask about?', thread=thread)}")


if __name__ == "__main__":
    asyncio.run(main())
