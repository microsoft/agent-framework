# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureAIAgentsProvider
from azure.identity.aio import AzureCliCredential
from pydantic import BaseModel, ConfigDict

"""
Azure AI Agent Provider Response Format Example

This sample demonstrates using AzureAIAgentsProvider with response_format
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
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        # Create agent with default response_format (WeatherInfo)
        agent = await provider.create_agent(
            name="StructuredReporter",
            instructions="Return structured JSON based on the requested format.",
            default_options={"response_format": WeatherInfo},
        )

        # Request 1: Uses default response_format from agent creation
        print("--- Request 1: Using default response_format (WeatherInfo) ---")
        query1 = "What's the weather like in Paris today?"
        print(f"User: {query1}")

        result1 = await agent.run(query1)

        if isinstance(result1.value, WeatherInfo):
            weather = result1.value
            print("Agent:")
            print(f"  Location: {weather.location}")
            print(f"  Temperature: {weather.temperature}")
            print(f"  Conditions: {weather.conditions}")
            print(f"  Recommendation: {weather.recommendation}")

        # Request 2: Override response_format at runtime with CityInfo
        print("\n--- Request 2: Runtime override with CityInfo ---")
        query2 = "Tell me about Tokyo."
        print(f"User: {query2}")

        result2 = await agent.run(query2, options={"response_format": CityInfo})

        if isinstance(result2.value, CityInfo):
            city = result2.value
            print("Agent:")
            print(f"  City: {city.city_name}")
            print(f"  Population: {city.population}")
            print(f"  Country: {city.country}")


if __name__ == "__main__":
    asyncio.run(main())
