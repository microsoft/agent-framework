# Copyright (c) Microsoft. All rights reserved.

import argparse
import asyncio
from contextlib import suppress
from random import randint
from typing import TYPE_CHECKING, Annotated, Literal

from agent_framework import ai_function, setup_logging
from agent_framework.observability import get_tracer, setup_observability
from agent_framework.openai import OpenAIResponsesClient
from opentelemetry import trace
from opentelemetry.trace.span import format_trace_id
from pydantic import Field

if TYPE_CHECKING:
    from agent_framework import ChatClientProtocol

"""
This sample, show how you can configure observability of an application via the
`setup_observability` function and inline parameters.

When you run this sample with an OTLP endpoint or an Application Insights connection string,
you should see traces, logs, and metrics in the configured backend.

If no OTLP endpoint or Application Insights connection string is configured, the sample will
output traces, logs, and metrics to the console.
"""

# Define the scenarios that can be run to show the telemetry data collected by the SDK
SCENARIOS = ["chat_client", "chat_client_stream", "ai_function", "all"]


async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    await asyncio.sleep(randint(0, 10) / 10.0)  # Simulate a network call
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def run_chat_client(client: "ChatClientProtocol", stream: bool = False) -> None:
    """Run an AI service.

    This function runs an AI service and prints the output.
    Telemetry will be collected for the service execution behind the scenes,
    and the traces will be sent to the configured telemetry backend.

    The telemetry will include information about the AI service execution.

    Args:
        client: The chat client to use.
        stream: Whether to use streaming for the response

    Remarks:
        For the scenario below, you should see the following:
        1 Client span, with 4 children:
            2 Internal span with gen_ai.operation.name=chat
                The first has finish_reason "tool_calls"
                The second has finish_reason "stop"
            2 Internal span with gen_ai.operation.name=execute_tool

    """
    scenario_name = "Chat Client Stream" if stream else "Chat Client"
    with get_tracer().start_as_current_span(name=f"Scenario: {scenario_name}", kind=trace.SpanKind.CLIENT):
        print("Running scenario:", scenario_name)
        message = "What's the weather in Amsterdam and in Paris?"
        print(f"User: {message}")
        if stream:
            print("Assistant: ", end="")
            async for chunk in client.get_streaming_response(message, tools=get_weather):
                if str(chunk):
                    print(str(chunk), end="")
            print("")
        else:
            response = await client.get_response(message, tools=get_weather)
            print(f"Assistant: {response}")


async def run_ai_function() -> None:
    """Run a AI function.

    This function runs a AI function and prints the output.
    Telemetry will be collected for the function execution behind the scenes,
    and the traces will be sent to the configured telemetry backend.

    The telemetry will include information about the AI function execution
    and the AI service execution.
    """
    with get_tracer().start_as_current_span("Scenario: AI Function", kind=trace.SpanKind.CLIENT):
        print("Running scenario: AI Function")
        func = ai_function(get_weather)
        weather = await func.invoke(location="Amsterdam")
        print(f"Weather in Amsterdam:\n{weather}")


async def main(scenario: Literal["chat_client", "chat_client_stream", "ai_function", "all"] = "all"):
    """Run the selected scenario(s)."""

    # Setup the logging with the more complete format
    setup_logging()
    # This will enable tracing and create the necessary tracing, logging and metrics providers
    # based on the provided parameters.
    setup_observability(
        enable_sensitive_data=True,
        # If you have set the `OTLP_ENDPOINT` environment variable and it'd different from the one below,
        # both endpoints will be used to create the OTLP exporter.
        # Same applies to the Application Insights connection string.
        otlp_endpoint=["http://localhost:4317/"],
    )

    with get_tracer().start_as_current_span("Sample Scenario's", kind=trace.SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

        client = OpenAIResponsesClient()

        # Scenarios where telemetry is collected in the SDK, from the most basic to the most complex.
        if scenario == "ai_function" or scenario == "all":
            with suppress(Exception):
                await run_ai_function()
        if scenario == "chat_client_stream" or scenario == "all":
            with suppress(Exception):
                await run_chat_client(client, stream=True)
        if scenario == "chat_client" or scenario == "all":
            with suppress(Exception):
                await run_chat_client(client, stream=False)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()

    arg_parser.add_argument(
        "--scenario",
        type=str,
        choices=SCENARIOS,
        default="all",
        help="The scenario to run. Default is all.",
    )

    args = arg_parser.parse_args()
    asyncio.run(main(args.scenario))
