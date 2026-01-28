# Copyright (c) Microsoft. All rights reserved.

import argparse
import asyncio
from contextlib import suppress
from random import randint
from typing import TYPE_CHECKING, Annotated, Literal

from agent_framework import tool, setup_logging
from agent_framework.observability import configure_otel_providers, get_tracer
from agent_framework.openai import OpenAIResponsesClient
from opentelemetry import trace
from opentelemetry.trace.span import format_trace_id
from pydantic import Field

if TYPE_CHECKING:
    from agent_framework import ChatClientProtocol

"""
This sample shows how you can configure observability with custom exporters passed directly
to the `configure_otel_providers()` function.

This approach gives you full control over exporter configuration (endpoints, headers, compression, etc.)
and allows you to add multiple exporters programmatically.

For standard OTLP setup, it's recommended to use environment variables (see configure_otel_providers_with_env_var.py).
Use this approach when you need custom exporter configuration beyond what environment variables provide.
"""

# Define the scenarios that can be run to show the telemetry data collected by the SDK
SCENARIOS = ["chat_client", "chat_client_stream", "tool", "all"]


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
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


async def run_tool() -> None:
    """Run a AI function.

    This function runs a AI function and prints the output.
    Telemetry will be collected for the function execution behind the scenes,
    and the traces will be sent to the configured telemetry backend.

    The telemetry will include information about the AI function execution
    and the AI service execution.
    """
    with get_tracer().start_as_current_span("Scenario: AI Function", kind=trace.SpanKind.CLIENT):
        print("Running scenario: AI Function")
        func = tool(get_weather)
        weather = await func.invoke(location="Amsterdam")
        print(f"Weather in Amsterdam:\n{weather}")


async def main(scenario: Literal["chat_client", "chat_client_stream", "tool", "all"] = "all"):
    """Run the selected scenario(s)."""

    # Setup the logging with the more complete format
    setup_logging()

    # Create custom OTLP exporters with specific configuration
    # Note: You need to install opentelemetry-exporter-otlp-proto-grpc or -http separately
    try:
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        # Create exporters with custom configuration
        # These will be added to any exporters configured via environment variables
        custom_exporters = [
            OTLPSpanExporter(endpoint="http://localhost:4317"),
            OTLPMetricExporter(endpoint="http://localhost:4317"),
            OTLPLogExporter(endpoint="http://localhost:4317"),
        ]
    except ImportError:
        print(
            "Warning: opentelemetry-exporter-otlp-proto-grpc not installed. "
            "Install with: pip install opentelemetry-exporter-otlp-proto-grpc"
        )
        print("Continuing without custom exporters...\n")
        custom_exporters = []

    # Setup observability with custom exporters and sensitive data enabled
    # The exporters parameter allows you to add custom exporters alongside
    # those configured via environment variables (OTEL_EXPORTER_OTLP_*)
    configure_otel_providers(
        enable_sensitive_data=True,
        exporters=custom_exporters,
    )

    with get_tracer().start_as_current_span("Sample Scenario's", kind=trace.SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

        client = OpenAIResponsesClient()

        # Scenarios where telemetry is collected in the SDK, from the most basic to the most complex.
        if scenario == "tool" or scenario == "all":
            with suppress(Exception):
                await run_tool()
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
