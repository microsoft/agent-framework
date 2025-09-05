#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.

"""
Example of using Agent Framework Debug UI with in-memory agent registration.

This demonstrates the simplest way to debug agents created in Python code.
"""

import asyncio
from typing import Annotated
from random import randint

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from devui import debug

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
    
    print("🚀 Agent Framework Debug UI - In-Memory Mode Example")
    print("="*60)
    
    # Create agents in code
    weather_agent = ChatAgent(
        name="WeatherAgent",
        description="Provides weather information and time",
        instructions="""
        You are a helpful weather and time assistant. Use the available tools
        to provide accurate weather information and current time for any location.
        """,
        chat_client=OpenAIChatClient(ai_model_id="gpt-4o-mini"),
        tools=[get_weather, get_time]
    )
    
    simple_agent = ChatAgent(
        name="SimpleAgent", 
        description="A simple conversational agent",
        instructions="You are a helpful assistant.",
        chat_client=OpenAIChatClient(ai_model_id="gpt-4o-mini")
    )
    
    print("Created 2 agents:")
    print(f"  • {weather_agent.name}: {weather_agent.description}")
    print(f"  • {simple_agent.name}: {simple_agent.description}")
    print()
    
    print("Starting debug UI...")
    print("  → Server will start on http://localhost:8080")
    print("  → Browser will open automatically")
    print("  → Available agents will be listed in the UI")
    print()
    
    # Launch debug UI with both agents
    debug(
        agents={
            "weather_agent": weather_agent,
            "simple_agent": simple_agent
        },
        port=8085,
        auto_open=True
    )

if __name__ == "__main__":
    main()