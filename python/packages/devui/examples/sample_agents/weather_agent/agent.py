# Copyright (c) Microsoft. All rights reserved.
"""Sample weather agent for Agent Framework Debug UI."""

import os
from typing import Annotated
from random import randint

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    temperature = randint(10, 30)
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {temperature}°C."

def get_forecast(
    location: Annotated[str, "The location to get the forecast for."],
    days: Annotated[int, "Number of days for forecast"] = 3
) -> str:
    """Get weather forecast for multiple days.""" 
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    forecast = []
    
    for day in range(1, days + 1):
        condition = conditions[randint(0, 3)]
        temp = randint(10, 30)
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
    chat_client=OpenAIChatClient(
        ai_model_id=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4o-mini")
    ),
    tools=[get_weather, get_forecast]
)