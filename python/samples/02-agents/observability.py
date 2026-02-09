# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import ChatAgent, tool
from agent_framework.observability import configure_otel_providers, get_tracer
from agent_framework.openai import OpenAIChatClient
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field

"""
Observability and Tracing

Demonstrates how to add OpenTelemetry-based observability to an agent.
Calling `configure_otel_providers()` enables tracing, logging, and metrics
based on environment variables.

Prerequisites:
- Set OTEL_EXPORTER_OTLP_ENDPOINT or other OTEL env vars (see .env.example)
- Or use the console exporter for local debugging

For more observability examples:
- Foundry tracing: getting_started/observability/agent_with_foundry_tracing.py
- Console output: getting_started/observability/advanced_manual_setup_console_output.py
- Zero-code setup: getting_started/observability/advanced_zero_code.py
- Env var config: getting_started/observability/configure_otel_providers_with_env_var.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/observability
"""


# <define_tool>
@tool(approval_mode="never_require")
async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    await asyncio.sleep(randint(0, 10) / 10.0)  # Simulate a network call
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."
# </define_tool>


async def main():
    # <configure_otel>
    # Enable tracing, logging, and metrics based on environment variables.
    # See .env.example for available OTEL configuration options.
    configure_otel_providers()
    # </configure_otel>

    questions = ["What's the weather in Amsterdam?", "and in Paris, and which is better?", "Why is the sky blue?"]

    # <traced_agent>
    with get_tracer().start_as_current_span("Scenario: Agent Chat", kind=SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

        agent = ChatAgent(
            chat_client=OpenAIChatClient(),
            tools=get_weather,
            name="WeatherAgent",
            instructions="You are a weather assistant.",
            id="weather-agent",
        )

        thread = agent.get_new_thread()
        for question in questions:
            print(f"\nUser: {question}")
            print(f"{agent.name}: ", end="")
            async for update in agent.run(question, thread=thread, stream=True):
                if update.text:
                    print(update.text, end="")
    # </traced_agent>


if __name__ == "__main__":
    asyncio.run(main())
