# Copyright (c) Microsoft. All rights reserved.

import asyncio

from dotenv import load_dotenv

"""AutoGen AssistantAgent vs Agent Framework Agent with function tools.

Demonstrates how to create and attach tools to agents in both frameworks.
"""

# Load environment variables from .env file
load_dotenv()


async def run_autogen() -> None:
    """AutoGen agent with a FunctionTool."""

    from autogen_agentchat.agents import AssistantAgent
    from autogen_core.tools import FunctionTool
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    # Define a simple tool function
    def get_weather(location: str) -> str:
        """Get the weather for a location.

        Args:
            location: The city name or location.

        Returns:
            A weather description.
        """
        return f"The weather in {location} is sunny and 72°F."

    # Wrap function in FunctionTool
    weather_tool = FunctionTool(
        func=get_weather,
        description="Get weather information for a location",
    )

    # Create agent with tool
    client = OpenAIChatCompletionClient(model="gpt-4.1-mini")
    agent = AssistantAgent(
        name="assistant",
        model_client=client,
        tools=[weather_tool],
        system_message="You are a helpful assistant. Use available tools to answer questions.",
    )

    # Run with tool usage
    result = await agent.run(task="What's the weather in Seattle?")
    print("[AutoGen]", result.messages[-1].to_text())


async def run_agent_framework() -> None:
    """Agent Framework agent with @tool decorator."""
    from agent_framework import Agent, tool
    from agent_framework.openai import OpenAIChatClient

    # Define tool with @tool decorator (automatic schema inference)
    # NOTE: approval_mode="never_require" is for sample brevity.
    @tool(approval_mode="never_require")
    def get_weather(location: str) -> str:
        """Get the weather for a location.

        Args:
            location: The city name or location.

        Returns:
            A weather description.
        """
        return f"The weather in {location} is sunny and 72°F."

    # Create agent with tool
    client = OpenAIChatClient(model="gpt-4.1-mini")
    agent = Agent(client=client,
        name="assistant",
        instructions="You are a helpful assistant. Use available tools to answer questions.",
        tools=[get_weather],
    )

    # Run with tool usage
    result = await agent.run("What's the weather in Seattle?")
    print("[Agent Framework]", result.text)


async def main() -> None:
    print("=" * 60)
    print("Assistant Agent with Tools Comparison")
    print("=" * 60)
    await run_autogen()
    print()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
