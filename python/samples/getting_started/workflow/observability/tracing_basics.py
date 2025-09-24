# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, get_logger, handler

"""Basic tracing workflow sample.

Sample: Workflow Tracing basics

A minimal two executor workflow demonstrates built in OpenTelemetry spans when diagnostics are enabled.
The sample raises an error if tracing is not configured.

Purpose:
- Require diagnostics by checking ENABLE_OTEL and wiring a console exporter.
- Show the span categories produced by a simple graph:
  - workflow.build (events: build.started, build.validation_completed, build.completed, edge_group.process)
  - workflow.run (events: workflow.started, workflow.completed or workflow.error)
  - executor.process (for each executor invocation)
  - message.send (for each outbound message)
- Provide a tiny flow that is easy to run and reason about: uppercase then print.

Prerequisites:
- No external services required for the workflow itself.
- To print spans to the console, install the OpenTelemetry SDK: pip install opentelemetry-sdk
- Enable diagnostics:
    configure your .env file with `ENABLE_OTEL=true` or run:
    export ENABLE_OTEL=true
"""

logger = get_logger()


def _ensure_tracing_configured() -> None:
    """Fail fast unless diagnostics are enabled and the SDK is present.

    If the env var is set, attach a ConsoleSpanExporter so spans print to stdout.
    """
    env = os.getenv("ENABLE_OTEL", "").lower()
    if env not in {"1", "true", "yes"}:
        logger.info("Tracing diagnostics are disabled in the env. Setting this manually here.")

    from agent_framework.observability import setup_observability
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    setup_observability(exporters=[ConsoleSpanExporter()])


class StartExecutor(Executor):
    @handler  # type: ignore[misc]
    async def handle_input(self, message: str, ctx: WorkflowContext[str]) -> None:
        # Transform and forward downstream. This produces executor.process and message.send spans.
        await ctx.send_message(message.upper())


class EndExecutor(Executor):
    @handler  # type: ignore[misc]
    async def handle_final(self, message: str, ctx: WorkflowContext) -> None:
        # Sink executor. The workflow completes when idle with no pending work.
        print(f"Final result: {message}")


async def main() -> None:
    _ensure_tracing_configured()  # Enforce tracing configuration before building or running the workflow.

    # Build a two node graph: StartExecutor -> EndExecutor. The builder emits a workflow.build span.
    workflow = (
        WorkflowBuilder()
        .add_edge(StartExecutor(id="start"), EndExecutor(id="end"))
        .set_start_executor("start")  # set_start_executor accepts an executor id string or the instance
        .build()
    )  # workflow.build span emitted here

    # Run once with a simple payload. You should see workflow.run plus executor and message spans.
    await workflow.run("hello tracing")  # workflow.run + executor.process and message.send spans


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
