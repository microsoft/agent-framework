# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIResponsesClient
from pydantic import BaseModel, Field


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    location: str
    weather: str | None = None


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main():
    print("=== OpenAI Responses Agent with Structured Output ===")

    # 1. Create an OpenAI Responses agent
    agent = ChatAgent(
        chat_client=OpenAIResponsesClient(),
        name="WeatherAgent",
        instructions="You are a helpful agent that provides weather information in structured format.",
        tools=[get_weather],
    )

    # 2. Ask the agent about weather information
    query = "What is the current weather in Seattle?"

    print(f"User: {query}")

    # 3. Get structured response from the agent using response_format parameter
    result = await agent.run(query, response_format=OutputStruct)

    # 4. Parse the structured output directly from the response text
    structured_data = OutputStruct.model_validate_json(result.text)

    print("Structured Output Agent:")
    print(f"Location: {structured_data.location}")
    print(f"Weather: {structured_data.weather}")
    print()

    # 5. Show the raw JSON structure as well
    print("Raw structured output:")
    print(structured_data.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
