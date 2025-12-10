# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, HostedWebSearchTool
from agent_framework.openai import OpenAIResponsesClient

"""
OpenAI Responses Client with Web Search Example

This sample demonstrates using HostedWebSearchTool with OpenAI Responses Client
for direct real-time information retrieval and current data access.
"""


async def main() -> None:
    # Test that the agent will use the web search tool with location
    additional_properties = {
        "user_location": {
            "country": "US",
            "city": "Seattle",
        }
    }

    agent = ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that can search the web for current information.",
        tools=[HostedWebSearchTool(additional_properties=additional_properties)],
    )

    message = "What is the current weather? Do not ask for my current location."
    stream = False
    print(f"User: {message}")

    if stream:
        print("Assistant: ", end="")
        async for chunk in agent.run_stream(message):
            if chunk.text:
                print(chunk.text, end="")
        print("")
    else:
        response = await agent.run(message)
        print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())
