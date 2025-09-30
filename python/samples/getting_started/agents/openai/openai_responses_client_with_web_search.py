# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import HostedWebSearchTool
from agent_framework.openai import OpenAIResponsesClient

"""
OpenAI Responses Client with Web Search Example

This sample demonstrates how to use web search capabilities with OpenAI Responses Client
for direct real-time information retrieval. The example includes:

- Integration with HostedWebSearchTool for internet search
- Direct response generation with web search results
- Real-time information gathering without agent orchestration
- Simplified interface for web-enhanced responses
- Current information retrieval and fact-checking

Web search with responses client provides a streamlined approach to
incorporating live web data into AI responses, ideal for applications
requiring current information without complex agent workflows.
"""


async def main() -> None:
    client = OpenAIResponsesClient()

    message = "What is the current weather? Do not ask for my current location."
    # Test that the client will use the web search tool with location
    additional_properties = {
        "user_location": {
            "country": "US",
            "city": "Seattle",
        }
    }
    stream = False
    print(f"User: {message}")
    if stream:
        print("Assistant: ", end="")
        async for chunk in client.get_streaming_response(
            message,
            tools=[HostedWebSearchTool(additional_properties=additional_properties)],
            tool_choice="auto",
        ):
            if chunk.text:
                print(chunk.text, end="")
        print("")
    else:
        response = await client.get_response(
            message,
            tools=[HostedWebSearchTool(additional_properties=additional_properties)],
            tool_choice="auto",
        )
        print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())
