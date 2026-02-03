# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.openai import OpenAIAssistantProvider
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict

"""
OpenAI Assistant Provider Response Format Example

This sample demonstrates using OpenAIAssistantProvider with response_format
for structured outputs in two ways:
1. Setting default response_format at agent creation time (default_options)
2. Overriding response_format at runtime (options parameter in agent.run)
"""


class WeatherInfo(BaseModel):
    """Structured weather information."""

    location: str
    temperature: int
    conditions: str
    recommendation: str
    model_config = ConfigDict(extra="forbid")


class CityInfo(BaseModel):
    """Structured city information."""

    city_name: str
    population: int
    country: str
    model_config = ConfigDict(extra="forbid")


async def main() -> None:
    """Example of using response_format at creation time and runtime."""

    async with (
        AsyncOpenAI() as client,
        OpenAIAssistantProvider(client) as provider,
    ):
        # Create agent with default response_format (WeatherInfo)
        agent = await provider.create_agent(
            name="StructuredReporter",
            model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            instructions="Return structured JSON based on the requested format.",
            default_options={"response_format": WeatherInfo},
        )

        try:
            # Request 1: Uses default response_format from agent creation
            print("--- Request 1: Using default response_format (WeatherInfo) ---")
            query1 = "What's the weather like in Paris today?"
            print(f"User: {query1}")

            result1 = await agent.run(query1)

            if weather := result1.try_parse_value(WeatherInfo):
                print("Agent:")
                print(f"  Location: {weather.location}")
                print(f"  Temperature: {weather.temperature}")
                print(f"  Conditions: {weather.conditions}")
                print(f"  Recommendation: {weather.recommendation}")
            else:
                print(f"Failed to parse response: {result1.text}")

            # Request 2: Override response_format at runtime with CityInfo
            print("\n--- Request 2: Runtime override with CityInfo ---")
            query2 = "Tell me about Tokyo."
            print(f"User: {query2}")

            result2 = await agent.run(query2, options={"response_format": CityInfo})

            if city := result2.try_parse_value(CityInfo):
                print("Agent:")
                print(f"  City: {city.city_name}")
                print(f"  Population: {city.population}")
                print(f"  Country: {city.country}")
            else:
                print(f"Failed to parse response: {result2.text}")
        finally:
            await client.beta.assistants.delete(agent.id)


if __name__ == "__main__":
    asyncio.run(main())
