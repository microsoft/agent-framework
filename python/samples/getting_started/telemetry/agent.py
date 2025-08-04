# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
import logging
from random import randint
from typing import Annotated

from agent_framework import ChatClientAgent
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
SCENARIOS = ["ai_service", "kernel_function", "auto_function_invocation", "all"]

if settings.connection_string:
    configure_azure_monitor(
        connection_string=settings.connection_string, enable_live_metrics=True, logger_name="agent_framework"
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
    # Set the logging level to INFO.
    logger.setLevel(logging.INFO)


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


async def main():
    # Set up the providers
    # This must be done before any other telemetry calls
    set_up_logging()
    set_up_tracing()
    set_up_metrics()

    tracer = trace.get_tracer("agent_framework")
    with tracer.start_as_current_span("Scenario: Agent Chat", kind=SpanKind.CLIENT) as current_span:
        print("Running scenario: Agent Chat")
        print("Welcome to the chat, type 'exit' to quit.")
        agent = ChatClientAgent(
            chat_client=OpenAIChatClient(),
            tools=get_weather,
            name="WeatherAgent",
            instructions="You are a weather assistant.",
        )
        thread = agent.get_new_thread()
        message = input("User: ")
        try:
            while message.lower() != "exit":
                print(f"{agent.display_name}: ", end="")
                async for update in agent.run_streaming(
                    message,
                    thread=thread,
                ):
                    if update.text:
                        print(update.text, end="")
                message = input("\nUser: ")
        except Exception as e:
            current_span.record_exception(e)
            print(f"\nError running interactive chat: {e}")


if __name__ == "__main__":
    asyncio.run(main())
