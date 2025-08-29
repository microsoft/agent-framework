# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import argparse
import asyncio
import logging
from contextlib import suppress
from random import randint
from typing import Annotated, Literal

from agent_framework import ChatClientBuilder, __version__, ai_function
from agent_framework.openai import OpenAIChatClient
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import DropAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.semconv.attributes import service_attributes
from opentelemetry.trace import SpanKind, set_tracer_provider
from opentelemetry.trace.span import format_trace_id
from pydantic import Field
from pydantic_settings import BaseSettings


class TelemetrySampleSettings(BaseSettings):
    """Settings for the telemetry sample application.

    Optional settings are:
    - connection_string: str - The connection string for the Application Insights resource.
                This value can be found in the Overview section when examining
                your resource from the Azure portal.
                (Env var CONNECTION_STRING)
    - otlp_endpoint: str - The OTLP endpoint to send telemetry data to.
                Depending on the exporter used, you may find this value in different places.
                (Env var OTLP_ENDPOINT)

    If no connection string or OTLP endpoint is provided, the telemetry data will be
    exported to the console.
    """

    connection_string: str | None = None
    otlp_endpoint: str | None = None


# Load settings
settings = TelemetrySampleSettings()

# Create a resource to represent the service/sample
resource = Resource.create({service_attributes.SERVICE_NAME: "TelemetryExample"})

# Define the scenarios that can be run
SCENARIOS = ["chat_client", "chat_client_stream", "ai_function", "all"]

if settings.connection_string:
    configure_azure_monitor(
        connection_string=settings.connection_string,
        enable_live_metrics=True,
        logger_name="agent_framework",
    )


def set_up_logging():
    class LogFilter(logging.Filter):
        """A filter to not process records from several subpackages."""

        # These are the namespaces that we want to exclude from logging for the purposes of this demo.
        namespaces_to_exclude: list[str] = [
            "httpx",
            "openai",
        ]

        def filter(self, record):
            return not any([record.name.startswith(namespace) for namespace in self.namespaces_to_exclude])

    exporters = []
    if settings.otlp_endpoint:
        exporters.append(OTLPLogExporter(endpoint=settings.otlp_endpoint))
    if not exporters:
        exporters.append(ConsoleLogExporter())

    # Create and set a global logger provider for the application.
    logger_provider = LoggerProvider(resource=resource)
    # Log processors are initialized with an exporter which is responsible
    # for sending the telemetry data to a particular backend.
    for log_exporter in exporters:
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    # Sets the global default logger provider
    set_logger_provider(logger_provider)

    # Create a logging handler to write logging records, in OTLP format, to the exporter.
    handler = LoggingHandler()
    handler.addFilter(LogFilter())
    # Attach the handler to the root logger. `getLogger()` with no arguments returns the root logger.
    # Events from all child loggers will be processed by this handler.
    logger = logging.getLogger()
    logger.addHandler(handler)
    # Set the logging level to NOTSET to allow all records to be processed by the handler.
    logger.setLevel(logging.NOTSET)


def set_up_tracing():
    exporters = []
    if settings.otlp_endpoint:
        exporters.append(OTLPSpanExporter(endpoint=settings.otlp_endpoint))
    if not exporters:
        exporters.append(ConsoleSpanExporter())

    # Initialize a trace provider for the application. This is a factory for creating tracers.
    tracer_provider = TracerProvider(resource=resource)
    # Span processors are initialized with an exporter which is responsible
    # for sending the telemetry data to a particular backend.
    for exporter in exporters:
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    # Sets the global default tracer provider
    set_tracer_provider(tracer_provider)


def set_up_metrics():
    exporters = []
    if settings.otlp_endpoint:
        exporters.append(OTLPMetricExporter(endpoint=settings.otlp_endpoint))
    if not exporters:
        exporters.append(ConsoleMetricExporter())

    # Initialize a metric provider for the application. This is a factory for creating meters.
    metric_readers = [
        PeriodicExportingMetricReader(metric_exporter, export_interval_millis=5000) for metric_exporter in exporters
    ]
    meter_provider = MeterProvider(
        metric_readers=metric_readers,
        resource=resource,
        views=[
            # Dropping all instrument names except for those starting with "agent_framework"
            View(instrument_name="*", aggregation=DropAggregation()),
            View(instrument_name="agent_framework*"),
        ],
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


async def run_chat_client(stream: bool = False, function_calling_outside: bool = False) -> None:
    """Run an AI service.

    This function runs an AI service and prints the output.
    Telemetry will be collected for the service execution behind the scenes,
    and the traces will be sent to the configured telemetry backend.

    The telemetry will include information about the AI service execution.

    Args:
        stream: Whether to use streaming for the plugin
        function_calling_outside: Whether to wrap the function calling outside the telemetry
            The difference between these is subtle but important.
            See more info below.

    Remarks:
        When function calling is outside the open telemetry loop
        each of the call to the model is handled as a seperate span,
        while when the open telemetry is put last, a single span
        is shown, which might include one or more rounds of function calling.

        So for the scenario below, with one function call result, and then a second `get_response` with those results,
        giving back a final result, you get the following:
        function_calling_outside == True:
            1 Client span, with 4 children:
                2 Internal span with gen_ai.operation.name=chat
                    The first has finish_reason "tool_calls"
                    The second has finish_reason "stop"
                2 Internal span with gen_ai.operation.name=execute_tool
            In this case there is one chat span, followed by two simultanous (and almost instant) execute_tool spans,
            followed by another chat span
        function_calling_outside == False:
            1 Client span, with 1 child:
                1 Internal span with gen_ai.operation.name=chat, with 2 children:
                    2 Internal spans with gen_ai.operation.name=execute_tool
                    and the finish_reason is "stop"
            In this case the Client span and the child are almost the same length.
        The total time for the client span is pretty much the same for both methods.
    """
    if function_calling_outside:
        client = (
            ChatClientBuilder(OpenAIChatClient())
            .open_telemetry_with(enable_otel_diagnostics_sensitive=True)
            .function_calling.build()
        )
        scenario_name = (
            "Chat Client Stream - Otel around function call loop"
            if stream
            else "Chat Client - Otel around function call loop"
        )
    else:
        client = (
            ChatClientBuilder(OpenAIChatClient())
            .function_calling.open_telemetry_with(enable_otel_diagnostics_sensitive=True)
            .build()
        )
        scenario_name = (
            "Chat Client Stream - Otel within function call loop"
            if stream
            else "Chat Client - Otel within function call loop"
        )

    tracer = trace.get_tracer("agent_framework", __version__)
    with tracer.start_as_current_span(name=f"Scenario: {scenario_name}", kind=SpanKind.CLIENT):
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

    tracer = trace.get_tracer("agent_framework", __version__)
    with tracer.start_as_current_span("Scenario: AI Function", kind=SpanKind.CLIENT):
        print("Running scenario: AI Function")
        func = ai_function(get_weather)
        weather = await func.invoke(location="Amsterdam")
        print(f"Weather in Amsterdam:\n{weather}")


async def main(scenario: Literal["chat_client", "chat_client_stream", "ai_function", "all"] = "all"):
    # Set up the providers
    # This must be done before any other telemetry calls
    set_up_logging()
    set_up_tracing()
    set_up_metrics()

    tracer = trace.get_tracer("agent_framework", __version__)
    with tracer.start_as_current_span("Scenario's", kind=SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

        # Scenarios where telemetry is collected in the SDK, from the most basic to the most complex.
        if scenario == "ai_function" or scenario == "all":
            with suppress(Exception):
                await run_ai_function()
        if scenario == "chat_client_stream" or scenario == "all":
            with suppress(Exception):
                await run_chat_client(stream=True, function_calling_outside=True)
            with suppress(Exception):
                await run_chat_client(stream=True, function_calling_outside=False)
        if scenario == "chat_client" or scenario == "all":
            with suppress(Exception):
                await run_chat_client(stream=False, function_calling_outside=True)
            with suppress(Exception):
                await run_chat_client(stream=False, function_calling_outside=False)


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
