# Copyright (c) Microsoft. All rights reserved.

"""Example of using Agent Framework DevUI with in-memory agent registration.

This demonstrates the simplest way to serve agents as OpenAI-compatible API endpoints.
"""

import logging
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.devui import serve
from agent_framework.openai import OpenAIChatClient


def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    temperature = 53
    return f"The weather in {location} is {conditions[0]} with a high of {temperature}°C."


def get_time(
    timezone: Annotated[str, "The timezone to get time for."] = "UTC",
) -> str:
    """Get current time for a timezone."""
    from datetime import datetime

    # Simplified for example
    return f"Current time in {timezone}: {datetime.now().strftime('%H:%M:%S')}"


def main():
    """Main function demonstrating in-memory agent registration."""
    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    # Create agents in code
    weather_agent = ChatAgent(
        name="weather-assistant",
        description="Provides weather information and time",
        instructions=(
            "You are a helpful weather and time assistant. Use the available tools to "
            "provide accurate weather information and current time for any location."
        ),
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

    logger.info("Starting DevUI on http://localhost:8090")
    logger.info("Entity IDs: agent_weather-assistant, agent_general-assistant")

    # Launch server with auto-generated entity IDs
    serve(entities=entities, port=8090, auto_open=True)


if __name__ == "__main__":
    main()
