# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.observability import get_tracer, setup_observability
from agent_framework.openai import OpenAIChatClient
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field

"""
This sample shows how you can observe an agent in Agent Framework by using the
same observability setup function to create HTTP/protobuf OTLP exporters.
By default Agent Framework uses gRPC exporters.

One common telemetry backend that uses this is Langfuse, you can setup a Langfuse Local instance with docker
and then set the following environment variables:
- OTEL_EXPORTER_OTLP_ENDPOINT
And optionally, if you have an API key:
- OTEL_EXPORTER_OTLP_HEADERS

The Exporters that are created below will use these environment variables to send data to the HTTP/protobuf endpoint.
Check the documentation for your particular endpoint to see what configuration is needed.
"""


async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    await asyncio.sleep(randint(0, 10) / 10.0)  # Simulate a network call
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main():
    # This will enable tracing and create the necessary tracing, logging and metrics providers
    # based on environment variables. See the .env.example file for the available configuration options.

    setup_observability(exporters=[OTLPSpanExporter(), OTLPMetricExporter(), OTLPLogExporter()])

    questions = ["What's the weather in Amsterdam?", "and in Paris, and which is better?", "Why is the sky blue?"]

    with get_tracer().start_as_current_span("Scenario: Agent Chat", kind=SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

        agent = ChatAgent(
            chat_client=OpenAIChatClient(),
            tools=get_weather,
            name="WeatherAgent",
            instructions="You are a weather assistant.",
        )
        thread = agent.get_new_thread()
        for question in questions:
            print(f"\nUser: {question}")
            print(f"{agent.display_name}: ", end="")
            async for update in agent.run_stream(
                question,
                thread=thread,
            ):
                if update.text:
                    print(update.text, end="")


if __name__ == "__main__":
    asyncio.run(main())
