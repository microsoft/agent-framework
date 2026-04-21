# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent, AgentResponse, AgentResponseUpdate, ResponseStream
from agent_framework.openai import OpenAIChatClient
from typing_extensions import Any

"""
This script demonstrates how to talk to a deployed agent using the OpenAIChatClient.

Depending on where you have deployed your agent (local or Foundry Hosting), you may
need to change the base_url when initializing the OpenAIChatClient.
"""


async def print_streaming_response(streaming_response: ResponseStream[AgentResponseUpdate, AgentResponse[Any]]) -> None:
    async for chunk in streaming_response:
        if chunk.text:
            print(chunk.text, end="", flush=True)


async def main() -> None:
    agent = Agent(client=OpenAIChatClient(base_url="http://localhost:8088"))
    session = agent.create_session()

    # First turn
    query = "Hi!"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    streaming_response = agent.run(query, session=session, stream=True)
    await print_streaming_response(streaming_response)

    # Second turn
    query = "Your name is Javis. What can you do?"
    print(f"\nUser: {query}")
    print("Agent: ", end="", flush=True)
    streaming_response = agent.run(query, session=session, stream=True)
    await print_streaming_response(streaming_response)

    # Third turn
    query = "What is your name?"
    print(f"\nUser: {query}")
    print("Agent: ", end="", flush=True)
    streaming_response = agent.run(query, session=session, stream=True)
    await print_streaming_response(streaming_response)


if __name__ == "__main__":
    asyncio.run(main())
