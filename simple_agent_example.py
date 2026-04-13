# Copyright (c) Microsoft. All rights reserved.

"""
Simple example agent that can greet users and tell jokes.
"""

import asyncio
import os
from typing import Annotated

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential


def tell_joke(topic: Annotated[str, "The topic for the joke"] = "general") -> str:
    """Tell a joke about a specific topic."""
    jokes = {
        "programming": "Why do programmers prefer dark mode? Because light attracts bugs!",
        "general": "Why don't scientists trust atoms? Because they make up everything!",
        "ai": "Why did the neural network go to therapy? It had too many layers of issues!",
    }
    return jokes.get(topic.lower(), jokes["general"])


def get_greeting(name: Annotated[str, "The name of the person to greet"]) -> str:
    """Generate a personalized greeting."""
    return f"Hello {name}! It's wonderful to meet you. How can I help you today?"


async def main():
    # Create an agent with tool functions
    agent = AzureOpenAIChatClient(
        endpoint="https://ppml-azure-openai-swedencentral.openai.azure.com",
        deployment_name="gpt-4o",
        credential=AzureCliCredential()
    ).create_agent(
        name="FriendlyAssistant",
        instructions="You are a friendly and helpful assistant. You can greet people and tell jokes.",
        tools=[tell_joke, get_greeting],
    )

    # Run some example interactions
    print("=" * 60)
    print("Example 1: Greeting")
    print("=" * 60)
    result = await agent.run("My name is Alex, can you greet me?")
    print(result)

    print("\n" + "=" * 60)
    print("Example 2: Tell a joke")
    print("=" * 60)
    result = await agent.run("Tell me a joke about programming")
    print(result)

    print("\n" + "=" * 60)
    print("Example 3: General conversation")
    print("=" * 60)
    result = await agent.run("What can you help me with?")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
