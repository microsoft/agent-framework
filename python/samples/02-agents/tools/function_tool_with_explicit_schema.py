# Copyright (c) Microsoft. All rights reserved.

"""
Function Tool with Explicit Schema Example

This example demonstrates how to provide an explicit schema to the @tool decorator
using the `schema` parameter, bypassing the automatic inference from the function
signature. This is useful when you want full control over the tool's parameter
schema that the AI model sees, or when the function signature does not accurately
represent the desired schema.

Two approaches are shown:
1. Using a Pydantic BaseModel subclass as the schema
2. Using a raw JSON schema dictionary as the schema
"""

import asyncio
from typing import Annotated

from agent_framework import tool
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env file
load_dotenv()


# Approach 1: Pydantic model as explicit schema
class WeatherInput(BaseModel):
    """Input schema for the weather tool."""

    location: Annotated[str, Field(description="The city name to get weather for")]
    unit: Annotated[str, Field(description="Temperature unit: celsius or fahrenheit")] = "celsius"


@tool(
    name="get_weather",
    description="Get the current weather for a given location.",
    schema=WeatherInput,
    approval_mode="never_require",
)
def get_weather(location: str, unit: str = "celsius") -> str:
    """Get the current weather for a location."""
    return f"The weather in {location} is 22 degrees {unit}."


# Approach 2: JSON schema dictionary as explicit schema
get_current_time_schema = {
    "type": "object",
    "properties": {
        "timezone": {"type": "string", "description": "The timezone to get the current time for", "default": "UTC"},
    },
}


@tool(
    name="get_current_time",
    description="Get the current time in a given timezone.",
    schema=get_current_time_schema,
    approval_mode="never_require",
)
def get_current_time(timezone: str = "UTC") -> str:
    """Get the current time."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return f"The current time in {timezone} is {datetime.now(ZoneInfo(timezone)).isoformat()}"


async def main():
    agent = OpenAIResponsesClient().as_agent(
        name="AssistantAgent",
        instructions="You are a helpful assistant. Use the available tools to answer questions.",
        tools=[get_weather, get_current_time],
    )

    query = "What is the weather in Seattle and what time is it?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())
