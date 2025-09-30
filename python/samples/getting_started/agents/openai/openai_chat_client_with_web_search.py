# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import HostedWebSearchTool
from agent_framework.openai import OpenAIChatClient

"""
OpenAI Chat Client with Web Search Example

This sample demonstrates how to use web search capabilities with OpenAI Chat Client
for real-time information retrieval. The example includes:

- Integration with HostedWebSearchTool for internet search
- Real-time web search and information gathering
- Using gpt-4o-search-preview model for enhanced search capabilities
- Combining conversational AI with live web data
- Current information retrieval and fact-checking

Web search integration enables agents to access current information,
making it ideal for answering questions about recent events,
current data, and real-time information queries.
"""


async def main() -> None:
    client = OpenAIChatClient(model_id="gpt-4o-search-preview")

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
