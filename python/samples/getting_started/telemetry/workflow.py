# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
import logging
from typing import Any

from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
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
from pydantic_settings import BaseSettings

"""Telemetry sample demonstrating OpenTelemetry integration with Agent Framework workflows.

This sample runs a simple sequential workflow with telemetry collection,
showing telemetry collection for workflow execution, executor processing,
and message publishing between executors.
"""


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
resource = Resource.create({service_attributes.SERVICE_NAME: "WorkflowTelemetryExample"})

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


# Executors for sequential workflow
class UpperCaseExecutor(Executor):
    """An executor that converts text to uppercase."""

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        """Execute the task by converting the input string to uppercase."""
        print(f"UpperCaseExecutor: Processing '{text}'")
        result = text.upper()
        print(f"UpperCaseExecutor: Result '{result}'")

        # Send the result to the next executor in the workflow.
        await ctx.send_message(result)


class ReverseTextExecutor(Executor):
    """An executor that reverses text."""

    @handler
    async def reverse_text(self, text: str, ctx: WorkflowContext[Any]) -> None:
        """Execute the task by reversing the input string."""
        print(f"ReverseTextExecutor: Processing '{text}'")
        result = text[::-1]
        print(f"ReverseTextExecutor: Result '{result}'")

        # Send the result with a workflow completion event.
        await ctx.add_event(WorkflowCompletedEvent(result))


async def run_sequential_workflow() -> None:
    """Run a simple sequential workflow demonstrating telemetry collection.

    This workflow processes a string through two executors in sequence:
    1. UpperCaseExecutor converts the input to uppercase
    2. ReverseTextExecutor reverses the string and completes the workflow

    Telemetry data collected includes:
    - Overall workflow execution spans
    - Individual executor processing spans
    - Message publishing between executors
    - Workflow completion events
    """

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("Scenario: Sequential Workflow", kind=SpanKind.CLIENT) as current_span:
        print("Running scenario: Sequential Workflow")
        try:
            # Step 1: Create the executors.
            upper_case_executor = UpperCaseExecutor(id="upper_case_executor")
            reverse_text_executor = ReverseTextExecutor(id="reverse_text_executor")

            # Step 2: Build the workflow with the defined edges.
            workflow = (
                WorkflowBuilder()
                .add_edge(upper_case_executor, reverse_text_executor)
                .set_start_executor(upper_case_executor)
                .build()
            )

            # Step 3: Run the workflow with an initial message.
            input_text = "hello world"
            print(f"Starting workflow with input: '{input_text}'")

            completion_event = None
            async for event in workflow.run_streaming(input_text):
                print(f"Event: {event}")
                if isinstance(event, WorkflowCompletedEvent):
                    # The WorkflowCompletedEvent contains the final result.
                    completion_event = event

            if completion_event:
                print(f"Workflow completed with result: '{completion_event.data}'")
            else:
                print("Workflow completed without a completion event")

        except Exception as e:
            current_span.record_exception(e)
            print(f"Error running workflow: {e}")


async def main():
    """Run the telemetry sample with a simple sequential workflow."""
    # Set up the providers
    # This must be done before any other telemetry calls
    set_up_logging()
    set_up_tracing()
    set_up_metrics()

    tracer = trace.get_tracer("agent_framework")
    with tracer.start_as_current_span("Sequential Workflow Scenario", kind=SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

        # Run the sequential workflow scenario
        await run_sequential_workflow()


if __name__ == "__main__":
    asyncio.run(main())
