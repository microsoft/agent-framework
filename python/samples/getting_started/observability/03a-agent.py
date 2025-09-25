# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.observability import get_tracer, setup_observability
from agent_framework.openai import OpenAIChatClient
from opentelemetry.trace import SpanKind
from pydantic import Field

"""
This sample shows you can can setup telemetry with a agent.
The agent invoke is a additional Semantic Convention that now
will wrap the calls made by the underlying chat client and tools.
"""


async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    await asyncio.sleep(randint(0, 10) / 10.0)  # Simulate a network call
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main():
    # Set up the telemetry

    questions = ["What's the weather in Amsterdam?", "and in Paris, and which is better?", "Why is the sky blue?"]
    setup_observability()
    with get_tracer().start_as_current_span("Scenario: Agent Chat", kind=SpanKind.CLIENT):
        print("Running scenario: Agent Chat")
        print("Welcome to the chat, type 'exit' to quit.")
        agent = ChatAgent(
            chat_client=OpenAIChatClient(),
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
