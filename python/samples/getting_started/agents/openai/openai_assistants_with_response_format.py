# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.openai import OpenAIAssistantProvider
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict

"""
OpenAI Assistant Provider Response Format Example

This sample demonstrates using OpenAIAssistantProvider with response_format
for structured outputs.
"""


class WeatherInfo(BaseModel):
    """Structured weather information."""

    location: str
    temperature: int
    conditions: str
    recommendation: str
    model_config = ConfigDict(extra="forbid")


async def main() -> None:
    """Example of using response_format with OpenAIAssistantProvider."""

    async with (
        AsyncOpenAI() as client,
        OpenAIAssistantProvider(client) as provider,
    ):
        agent = await provider.create_agent(
            name="WeatherReporter",
            model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            instructions="You provide weather reports in structured JSON format.",
            response_format=WeatherInfo,
        )

        try:
            query = "What's the weather like in Paris today?"
            print(f"User: {query}")

            result = await agent.run(query)

            if isinstance(result.value, WeatherInfo):
                weather = result.value
                print("Agent:")
                print(f"  Location: {weather.location}")
                print(f"  Temperature: {weather.temperature}")
                print(f"  Conditions: {weather.conditions}")
                print(f"  Recommendation: {weather.recommendation}")
        finally:
            await client.beta.assistants.delete(agent.id)


if __name__ == "__main__":
    asyncio.run(main())
