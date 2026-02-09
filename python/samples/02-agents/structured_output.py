# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentResponse
from agent_framework.openai import OpenAIResponsesClient
from pydantic import BaseModel

"""
Structured Output from an Agent

Demonstrates how to get typed, structured responses from an agent using Pydantic models.
The agent returns data that is automatically parsed into your model class, enabling
type-safe access to response fields.

Covers both non-streaming and streaming modes with response_format.

For more on structured output:
- Deeper sample: getting_started/agents/openai/openai_responses_client_with_structured_output.py
- Azure AI response format: getting_started/agents/azure_ai/azure_ai_with_response_format.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/structured-output
"""


# <output_model>
class CityInfo(BaseModel):
    """Structured output model for city information."""

    city: str
    country: str
    description: str
# </output_model>


async def non_streaming_example() -> None:
    """Get structured output from a non-streaming agent call."""
    print("=== Non-streaming Structured Output ===")

    # <create_agent>
    agent = OpenAIResponsesClient().as_agent(
        name="CityAgent",
        instructions="You are a helpful agent that describes cities in a structured format.",
    )
    # </create_agent>

    query = "Tell me about Paris, France"
    print(f"User: {query}")

    # <structured_response>
    result = await agent.run(query, options={"response_format": CityInfo})

    if structured_data := result.value:
        print(f"City: {structured_data.city}")
        print(f"Country: {structured_data.country}")
        print(f"Description: {structured_data.description}")
    else:
        print(f"Could not parse response: {result.text}")
    # </structured_response>


async def streaming_example() -> None:
    """Get structured output from a streaming agent call."""
    print("\n=== Streaming Structured Output ===")

    agent = OpenAIResponsesClient().as_agent(
        name="CityAgent",
        instructions="You are a helpful agent that describes cities in a structured format.",
    )

    query = "Tell me about Tokyo, Japan"
    print(f"User: {query}")

    # <streaming_structured>
    result = await AgentResponse.from_update_generator(
        agent.run(query, stream=True, options={"response_format": CityInfo}),
        output_format_type=CityInfo,
    )

    if structured_data := result.value:
        print(f"City: {structured_data.city}")
        print(f"Country: {structured_data.country}")
        print(f"Description: {structured_data.description}")
    else:
        print(f"Could not parse response: {result.text}")
    # </streaming_structured>


async def main() -> None:
    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
