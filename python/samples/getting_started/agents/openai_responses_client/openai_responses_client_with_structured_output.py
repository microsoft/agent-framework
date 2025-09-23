# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.openai import OpenAIResponsesClient
from pydantic import BaseModel


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    city: str
    description: str


async def main():
    print("=== OpenAI Responses Agent with Structured Output ===")

    # 1. Create an OpenAI Responses agent
    agent = OpenAIResponsesClient().create_agent(
        name="CityAgent",
        instructions="You are a helpful agent that describes cities in a structured format.",
    )

    # 2. Ask the agent about a city
    query = "Tell me about Paris, France"

    print(f"User: {query}")

    # 3. Get structured response from the agent using response_format parameter
    result = await agent.run(query, response_format=OutputStruct)

    # 4. Access the structured output directly from the response value
    if result.value:
        structured_data = result.value
        print("Structured Output Agent (from result.value):")
        print(f"City: {structured_data.city}")
        print(f"Description: {structured_data.description}")
    else:
        print("Error: No structured data found in result.value")


if __name__ == "__main__":
    asyncio.run(main())
