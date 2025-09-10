# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
import logging
from random import randint
from typing import Annotated

from agent_framework.openai import OpenAIChatClient
from opentelemetry._logs import set_logger_provider
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import set_tracer_provider
from pydantic import Field

"""
This sample shows how to manually set up OpenTelemetry to log to the console.
And this can also be used as a reference for more complex telemetry setups.
"""

resource = Resource.create({ResourceAttributes.SERVICE_NAME: "ManualSetup"})


def setup_console_telemetry():
    # Create and set a global logger provider for the application.
    logger_provider = LoggerProvider(resource=resource)
    # Log processors are initialized with an exporter which is responsible
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(ConsoleLogExporter()))
    # Sets the global default logger provider
    set_logger_provider(logger_provider)

    # Create a logging handler to write logging records, in OTLP format, to the exporter.
    handler = LoggingHandler()
    # Attach the handler to the root logger. `getLogger()` with no arguments returns the root logger.
    # Events from all child loggers will be processed by this handler.
    logger = logging.getLogger()
    logger.addHandler(handler)
    # Set the logging level to NOTSET to allow all records to be processed by the handler.
    logger.setLevel(logging.NOTSET)
    # Initialize a trace provider for the application. This is a factory for creating tracers.
    tracer_provider = TracerProvider(resource=resource)
    # Span processors are initialized with an exporter which is responsible
    # for sending the telemetry data to a particular backend.
    tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    # Sets the global default tracer provider
    set_tracer_provider(tracer_provider)
    # Initialize a metric provider for the application. This is a factory for creating meters.
    meter_provider = MeterProvider(
        metric_readers=[PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=5000)],
        resource=resource,
    )
    # Sets the global default meter provider
    set_meter_provider(meter_provider)


async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    await asyncio.sleep(randint(0, 10) / 10.0)  # Simulate a network call
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def run_chat_client() -> None:
    """Run an AI service.

    This function runs an AI service and prints the output.
    Telemetry will be collected for the service execution behind the scenes,
    and the traces will be sent to the configured telemetry backend.

    The telemetry will include information about the AI service execution.

    Args:
        stream: Whether to use streaming for the plugin

    Remarks:
        When function calling is outside the open telemetry loop
        each of the call to the model is handled as a seperate span,
        while when the open telemetry is put last, a single span
        is shown, which might include one or more rounds of function calling.

        So for the scenario below, you should see the following:

        2 spans with gen_ai.operation.name=chat
            The first has finish_reason "tool_calls"
            The second has finish_reason "stop"
        2 spans with gen_ai.operation.name=execute_tool

    """
    client = OpenAIChatClient()
    message = "What's the weather in Amsterdam and in Paris?"
    print(f"User: {message}")
    print("Assistant: ", end="")
    async for chunk in client.get_streaming_response(message, tools=get_weather):
        if str(chunk):
            print(str(chunk), end="")
    print("")


async def main():
    """Run the selected scenario(s)."""
    setup_console_telemetry()
    await run_chat_client()


if __name__ == "__main__":
    asyncio.run(main())
