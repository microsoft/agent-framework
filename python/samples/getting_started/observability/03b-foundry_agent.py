# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.observability import get_tracer
from agent_framework_foundry import FoundryChatClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from opentelemetry.trace import SpanKind
from pydantic import Field

"""
This sample shows you can can setup telemetry with a agent from Foundry.
We once again call the `setup_foundry_observability` method to set up telemetry in order to include the overall spans.
"""


async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    await asyncio.sleep(randint(0, 10) / 10.0)  # Simulate a network call
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main():
    # Set up the providers
    # This must be done before any other telemetry calls
    questions = ["What's the weather in Amsterdam?", "and in Paris, and which is better?", "Why is the sky blue?"]
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential) as project,
        # this calls `setup_foundry_observability` through the context manager
        FoundryChatClient(client=project) as client,
    ):
        await client.setup_foundry_observability(enable_live_metrics=True)
        with get_tracer().start_as_current_span("Single Agent Chat", kind=SpanKind.CLIENT):
            print("Running Single Agent Chat")
            print("Welcome to the chat, type 'exit' to quit.")
            agent = ChatAgent(
                chat_client=client,
                tools=get_weather,
                name="WeatherAgent",
                instructions="You are a weather assistant.",
            )
            thread = agent.get_new_thread()
            for question in questions:
                print(f"User: {question}")
                print(f"{agent.display_name}: ", end="")
                async for update in agent.run_stream(
                    question,
                    thread=thread,
                ):
                    if update.text:
                        print(update.text, end="")


if __name__ == "__main__":
    asyncio.run(main())
