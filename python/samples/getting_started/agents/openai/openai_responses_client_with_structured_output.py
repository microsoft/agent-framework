# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentResponse
from agent_framework.openai import OpenAIResponsesClient
from pydantic import BaseModel

"""
OpenAI Responses Client with Structured Output Example

This sample demonstrates using structured output capabilities with OpenAI Responses Client,
showing Pydantic model integration for type-safe response parsing and data extraction.
"""


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    city: str
    description: str


async def non_streaming_example() -> None:
    print("=== Non-streaming example ===")

    # Create an OpenAI Responses agent
    agent = OpenAIResponsesClient().as_agent(
        name="CityAgent",
        instructions="You are a helpful agent that describes cities in a structured format.",
    )

    # Ask the agent about a city
    query = "Tell me about Paris, France"
    print(f"User: {query}")

    # Get structured response from the agent using response_format parameter
    result = await agent.run(query, options={"response_format": OutputStruct})

    # Access the structured output using the parsed value
    if structured_data := result.value:
        print("Structured Output Agent:")
        print(f"City: {structured_data.city}")
        print(f"Description: {structured_data.description}")
    else:
        print(f"Failed to parse response: {result.text}")


async def streaming_example() -> None:
    print("=== Streaming example ===")

    # Create an OpenAI Responses agent
    agent = OpenAIResponsesClient().as_agent(
        name="CityAgent",
        instructions="You are a helpful agent that describes cities in a structured format.",
    )

    # Ask the agent about a city
    query = "Tell me about Tokyo, Japan"
    print(f"User: {query}")

    # Get structured response from streaming agent using AgentResponse.from_agent_response_generator
    # This method collects all streaming updates and combines them into a single AgentResponse
    result = await AgentResponse.from_agent_response_generator(
        agent.run_stream(query, options={"response_format": OutputStruct}),
        output_format_type=OutputStruct,
    )

    # Access the structured output using the parsed value
    if structured_data := result.value:
        print("Structured Output (from streaming with AgentResponse.from_agent_response_generator):")
        print(f"City: {structured_data.city}")
        print(f"Description: {structured_data.description}")
    else:
        print(f"Failed to parse response: {result.text}")


async def main() -> None:
    print("=== OpenAI Responses Agent with Structured Output ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
