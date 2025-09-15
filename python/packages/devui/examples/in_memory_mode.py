#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.

"""Example of using Agent Framework DevUI with in-memory agent registration.

This demonstrates the simplest way to serve agents as OpenAI-compatible API endpoints.
"""

from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

from agent_framework_devui import serve


def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    temperature = randint(10, 30)
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {temperature}°C."


def get_time(
    timezone: Annotated[str, "The timezone to get time for."] = "UTC",
) -> str:
    """Get current time for a timezone."""
    from datetime import datetime

    # Simplified for example
    return f"Current time in {timezone}: {datetime.now().strftime('%H:%M:%S')}"


def main():
    """Main function demonstrating in-memory agent registration."""
    # Create agents in code
    weather_agent = ChatAgent(
        name="weather-assistant",
        description="Provides weather information and time",
        instructions="You are a helpful weather and time assistant. Use the available tools to provide accurate weather information and current time for any location.",
        chat_client=OpenAIChatClient(ai_model_id="gpt-4o-mini"),
        tools=[get_weather, get_time],
    )

    simple_agent = ChatAgent(
        name="general-assistant",
        description="A simple conversational agent",
        instructions="You are a helpful assistant.",
        chat_client=OpenAIChatClient(ai_model_id="gpt-4o-mini"),
    )

    # Collect entities for serving
    entities = [weather_agent, simple_agent]

    print("Starting DevUI on http://localhost:8090")
    print("Entity IDs: agent_weather-assistant, agent_general-assistant")

    # Launch server with auto-generated entity IDs
    serve(entities=entities, port=8090, auto_open=True)


if __name__ == "__main__":
    main()
