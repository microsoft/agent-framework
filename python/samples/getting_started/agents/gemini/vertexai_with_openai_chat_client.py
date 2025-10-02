# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

import google.auth.transport.requests
from agent_framework.openai import OpenAIChatClient
from google.auth import default, transport

"""
Vertex AI with OpenAI Chat Client Example

This sample demonstrates using Gemini models on Vertex AI through OpenAI Chat Client by
configuring the base URL to point to Google's API for cross-provider compatibility.
"""


def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    # Get an access token
    credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(google.auth.transport.requests.Request())

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    model_id = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    agent = OpenAIChatClient(
        api_key=credentials.token,
        base_url=f"https://aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/endpoints/openapi/",
        model_id=f"google/{model_id}",
    ).create_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")


async def main() -> None:
    print("=== Gemini with OpenAI Chat Client Agent Example ===")

    await non_streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
