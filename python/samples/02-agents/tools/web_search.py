# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, HostedWebSearchTool
from agent_framework.openai import OpenAIResponsesClient

"""
Web Search Tool

Demonstrates using HostedWebSearchTool to give the agent access to real-time
web search for current information retrieval.

For more on web search:
- OpenAI chat client: getting_started/agents/openai/openai_chat_client_with_web_search.py
- Azure AI: getting_started/agents/azure_ai/azure_ai_with_web_search.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/web-search
"""


async def main() -> None:
    print("=== Web Search Tool ===\n")

    # <create_agent>
    agent = ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that can search the web for current information.",
        tools=[
            HostedWebSearchTool(
                additional_properties={
                    "user_location": {
                        "country": "US",
                        "city": "Seattle",
                    }
                }
            )
        ],
    )
    # </create_agent>

    # <run_query>
    message = "What is the current weather? Do not ask for my current location."
    print(f"User: {message}")
    response = await agent.run(message)
    print(f"Assistant: {response}")
    # </run_query>


if __name__ == "__main__":
    asyncio.run(main())
