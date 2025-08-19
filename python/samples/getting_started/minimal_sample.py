# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework.openai import OpenAIChatClient


def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


agent = OpenAIChatClient().create_agent(
    name="WeatherAgent", instructions="You are a helpful weather agent.", tools=get_weather
)
print(asyncio.run(agent.run("What's the weather like in Seattle?")))
