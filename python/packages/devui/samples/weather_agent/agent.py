# Copyright (c) Microsoft. All rights reserved.
"""Sample weather agent for Agent Framework Debug UI."""

import os
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient


def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    temperature = 53
    return f"The weather in {location} is {conditions[0]} with a high of {temperature}°C."


def get_forecast(
    location: Annotated[str, "The location to get the forecast for."],
    days: Annotated[int, "Number of days for forecast"] = 3,
) -> str:
    """Get weather forecast for multiple days."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    forecast = []

    for day in range(1, days + 1):
        condition = conditions[0]
        temp = 53
        forecast.append(f"Day {day}: {condition}, {temp}°C")

    return f"Weather forecast for {location}:\n" + "\n".join(forecast)


# Agent instance following Agent Framework conventions
agent = ChatAgent(
    name="WeatherAgent",
    description="A helpful agent that provides weather information and forecasts",
    instructions="""
    You are a weather assistant. You can provide current weather information
    and forecasts for any location. Always be helpful and provide detailed
    weather information when asked.
    """,
    chat_client=OpenAIChatClient(ai_model_id=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4o")),
    tools=[get_weather, get_forecast],
)


def main():
    """Launch the weather agent in DevUI."""
    import logging

    from agent_framework.devui import serve

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting Weather Agent")
    logger.info("Available at: http://localhost:8090")
    logger.info("Entity ID: agent_WeatherAgent")

    # Launch server with the agent
    serve(entities=[agent], port=8090, auto_open=True)


if __name__ == "__main__":
    main()
