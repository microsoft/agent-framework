# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
from typing import Any

from agent_framework.telemetry import setup_telemetry
from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id

"""Telemetry sample demonstrating OpenTelemetry integration with Agent Framework workflows.

This sample runs a simple sequential workflow with telemetry collection,
showing telemetry collection for workflow execution, executor processing,
and message publishing between executors.
"""


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
            async for event in workflow.run_stream(input_text):
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

    setup_telemetry()

    tracer = trace.get_tracer("agent_framework")
    with tracer.start_as_current_span("Sequential Workflow Scenario", kind=SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

        # Run the sequential workflow scenario
        await run_sequential_workflow()


if __name__ == "__main__":
    asyncio.run(main())
