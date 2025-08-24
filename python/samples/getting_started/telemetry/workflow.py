# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal

from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    WorkflowEvent,
    WorkflowExecutor,
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


# Message types for sub-workflow scenario
@dataclass
class TextProcessingRequest:
    """Request to process a text string."""

    text: str
    task_id: str


@dataclass
class TextProcessingResult:
    """Result of text processing."""

    task_id: str
    text: str
    word_count: int
    char_count: int


class AllTasksCompleted(WorkflowEvent):
    """Event triggered when all processing tasks are complete."""

    def __init__(self, results: list[TextProcessingResult]):
        super().__init__(results)


# Executors for sequential workflow scenario
class UpperCaseExecutor(Executor):
    """An executor that converts text to uppercase."""

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        """Execute the task by converting the input string to uppercase."""
        print(f"🔤 UpperCaseExecutor: Processing '{text}'")
        result = text.upper()
        print(f"🔤 UpperCaseExecutor: Result '{result}'")

        # Send the result to the next executor in the workflow.
        await ctx.send_message(result)


class ReverseTextExecutor(Executor):
    """An executor that reverses text."""

    @handler
    async def reverse_text(self, text: str, ctx: WorkflowContext[Any]) -> None:
        """Execute the task by reversing the input string."""
        print(f"🔄 ReverseTextExecutor: Processing '{text}'")
        result = text[::-1]
        print(f"🔄 ReverseTextExecutor: Result '{result}'")

        # Send the result with a workflow completion event.
        await ctx.add_event(WorkflowCompletedEvent(result))


# Sub-workflow executor
class TextProcessor(Executor):
    """Processes text strings - counts words and characters."""

    def __init__(self):
        super().__init__(id="text_processor")

    @handler
    async def process_text(
        self, request: TextProcessingRequest, ctx: WorkflowContext[TextProcessingResult]
    ) -> None:
        """Process a text string and return statistics."""
        text_preview = f"'{request.text[:50]}{'...' if len(request.text) > 50 else ''}'"
        print(f"🔍 Sub-workflow processing text (Task {request.task_id}): {text_preview}")

        # Simple text processing
        word_count = len(request.text.split()) if request.text.strip() else 0
        char_count = len(request.text)

        print(f"📊 Task {request.task_id}: {word_count} words, {char_count} characters")

        # Create result
        result = TextProcessingResult(
            task_id=request.task_id,
            text=request.text,
            word_count=word_count,
            char_count=char_count,
        )

        print(f"✅ Sub-workflow completed task {request.task_id}")
        # Signal completion
        await ctx.add_event(WorkflowCompletedEvent(data=result))


# Parent workflow orchestrator
class TextProcessingOrchestrator(Executor):
    """Orchestrates multiple text processing tasks using sub-workflows."""

    results: list[TextProcessingResult] = []
    expected_count: int = 0

    def __init__(self):
        super().__init__(id="text_orchestrator")

    @handler
    async def start_processing(
        self, texts: list[str], ctx: WorkflowContext[TextProcessingRequest]
    ) -> None:
        """Start processing multiple text strings."""
        print(f"📄 Starting processing of {len(texts)} text strings")
        print("=" * 60)

        self.expected_count = len(texts)

        # Send each text to a sub-workflow
        for i, text in enumerate(texts):
            task_id = f"task_{i + 1}"
            request = TextProcessingRequest(text=text, task_id=task_id)
            print(f"📤 Dispatching {task_id} to sub-workflow")
            await ctx.send_message(request, target_id="text_processor_workflow")

    @handler
    async def collect_result(
        self, result: TextProcessingResult, ctx: WorkflowContext[None]
    ) -> None:
        """Collect results from sub-workflows."""
        print(f"📥 Collected result from {result.task_id}")
        self.results.append(result)

        # Check if all results are collected
        if len(self.results) == self.expected_count:
            print("\n🎉 All tasks completed!")
            await ctx.add_event(AllTasksCompleted(self.results))

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all processing results."""
        total_words = sum(result.word_count for result in self.results)
        total_chars = sum(result.char_count for result in self.results)
        avg_words = total_words / len(self.results) if self.results else 0
        avg_chars = total_chars / len(self.results) if self.results else 0

        return {
            "total_texts": len(self.results),
            "total_words": total_words,
            "total_characters": total_chars,
            "average_words_per_text": round(avg_words, 2),
            "average_characters_per_text": round(avg_chars, 2),
        }


async def run_sequential_workflow() -> None:
    """Run a sequential workflow with telemetry.

    This function runs a workflow with two executors that process a string in sequence.
    The first executor converts the input string to uppercase, and the second executor
    reverses the string. Telemetry will be collected for the workflow execution behind
    the scenes, and the traces will be sent to the configured telemetry backend.

    The telemetry will include information about:
    - Overall workflow execution
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


async def run_sub_workflow() -> None:
    """Run a sub-workflow scenario with telemetry.

    This function runs a workflow that demonstrates sub-workflows with telemetry.
    The parent workflow orchestrates multiple text processing tasks, where each
    task is handled by a sub-workflow. Telemetry will be collected for the
    workflow execution behind the scenes, and the traces will be sent to the
    configured telemetry backend.

    The telemetry will include information about:
    - Parent workflow execution spans
    - Sub-workflow execution spans
    - Message passing between parent and sub-workflows
    - WorkflowExecutor spans for sub-workflow invocation
    - Event processing across workflow boundaries
    """

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("Scenario: Sub-Workflow", kind=SpanKind.CLIENT) as current_span:
        print("Running scenario: Sub-Workflow")
        try:
            # Step 1: Create the text processing sub-workflow
            text_processor = TextProcessor()

            processing_workflow = (
                WorkflowBuilder()
                .set_start_executor(text_processor)
                .build()
            )

            print("🔧 Setting up parent workflow...")

            # Step 2: Create the parent workflow
            orchestrator = TextProcessingOrchestrator()
            workflow_executor = WorkflowExecutor(processing_workflow, id="text_processor_workflow")

            main_workflow = (
                WorkflowBuilder()
                .set_start_executor(orchestrator)
                .add_edge(orchestrator, workflow_executor)
                .add_edge(workflow_executor, orchestrator)
                .build()
            )

            # Step 3: Test data - various text strings
            test_texts = [
                "Hello world! This is a simple test.",
                "Python telemetry with workflows.",
                "Short text.",
                "This demonstrates sub-workflow telemetry in Agent Framework.",
            ]

            print(f"\n🧪 Testing with {len(test_texts)} text strings")
            print("=" * 60)

            # Step 4: Run the workflow
            completion_event = None
            async for event in main_workflow.run_streaming(test_texts):
                print(f"Event: {event}")
                if isinstance(event, AllTasksCompleted):
                    completion_event = event

            # Step 5: Display results
            if completion_event:
                print("\n📊 Processing Results:")
                print("=" * 60)

                # Sort results by task_id for consistent display
                sorted_results = sorted(completion_event.data, key=lambda r: r.task_id)

                for result in sorted_results:
                    preview = result.text[:30] + "..." if len(result.text) > 30 else result.text
                    preview = preview.replace("\n", " ").strip() or "(empty)"
                    print(f"✅ {result.task_id}: '{preview}' -> {result.word_count} words, {result.char_count} chars")

                # Step 6: Display summary
                summary = orchestrator.get_summary()
                print("\n📈 Summary:")
                print("=" * 60)
                print(f"📄 Total texts processed: {summary['total_texts']}")
                print(f"📝 Total words: {summary['total_words']}")
                print(f"🔤 Total characters: {summary['total_characters']}")
                print(f"📊 Average words per text: {summary['average_words_per_text']}")
                print(f"📏 Average characters per text: {summary['average_characters_per_text']}")

                print("\n🏁 Sub-workflow processing complete!")

        except Exception as e:
            current_span.record_exception(e)
            print(f"Error running sub-workflow: {e}")


async def main(scenario: Literal["sequential", "sub_workflow", "all"] = "all"):
    # Set up the providers
    # This must be done before any other telemetry calls
    set_up_logging()
    set_up_tracing()
    set_up_metrics()

    tracer = trace.get_tracer("agent_framework")
    with tracer.start_as_current_span("Workflow Scenarios", kind=SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

        # Scenarios where telemetry is collected for workflow execution
        if scenario == "sequential" or scenario == "all":
            await run_sequential_workflow()
            print("\n" + "=" * 60 + "\n")

        if scenario == "sub_workflow" or scenario == "all":
            await run_sub_workflow()


if __name__ == "__main__":
    import argparse

    arg_parser = argparse.ArgumentParser(
        description="Workflow telemetry sample demonstrating OpenTelemetry integration with Agent Framework workflows."
    )
    arg_parser.add_argument(
        "--scenario",
        type=str,
        choices=["sequential", "sub_workflow", "all"],
        default="all",
        help="The scenario to run. Default is all.",
    )

    args = arg_parser.parse_args()
    asyncio.run(main(args.scenario))
