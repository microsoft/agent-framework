# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureAIAgentsProvider
from azure.identity.aio import AzureCliCredential
from pydantic import BaseModel, ConfigDict

"""
Azure AI Agent Provider Response Format Example

This sample demonstrates using AzureAIAgentsProvider with default_options
containing response_format for structured outputs.
"""


class WeatherInfo(BaseModel):
    """Structured weather information."""

    location: str
    temperature: int
    conditions: str
    recommendation: str
    model_config = ConfigDict(extra="forbid")


async def main() -> None:
    """Example of using default_options with response_format in AzureAIAgentsProvider."""

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="WeatherReporter",
            instructions="You provide weather reports in structured JSON format.",
            default_options={"response_format": WeatherInfo},
        )

        query = "What's the weather like in Paris today?"
        print(f"User: {query}")

        result = await agent.run(query)

        if isinstance(result.value, WeatherInfo):
            weather = result.value
            print("Agent:")
            print(f"Location: {weather.location}")
            print(f"Temperature: {weather.temperature}")
            print(f"Conditions: {weather.conditions}")
            print(f"Recommendation: {weather.recommendation}")


if __name__ == "__main__":
    asyncio.run(main())
