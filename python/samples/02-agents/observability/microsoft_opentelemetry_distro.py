# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import get_tracer
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from microsoft.opentelemetry import use_microsoft_opentelemetry
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field

# Load environment variables from .env file
load_dotenv()


@tool(approval_mode="never_require")
async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    await asyncio.sleep(randint(0, 10) / 10.0)  # Simulate a network call
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main():
    # Set up Azure monitor exporters for telemetry
    # This will automatically enable instrumentation for Agent Framework
    # Install the Microsoft OpenTelemetry Distro package to enable this functionality:
    # pip install microsoft-opentelemetry
    use_microsoft_opentelemetry(enable_azure_monitor=True)

    questions = ["What's the weather in Amsterdam?", "and in Paris, and which is better?", "Why is the sky blue?"]

    with get_tracer().start_as_current_span("Scenario: Agent Chat", kind=SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

        agent = Agent(
            client=FoundryChatClient(credential=AzureCliCredential()),
            tools=get_weather,
            name="WeatherAgent",
            instructions="You are a weather assistant.",
            id="weather-agent",
        )
        session = agent.create_session()
        for question in questions:
            print(f"\nUser: {question}")
            print(f"{agent.name}: ", end="")
            async for update in agent.run(question, session=session, stream=True):
                if update.text:
                    print(update.text, end="")


if __name__ == "__main__":
    asyncio.run(main())
