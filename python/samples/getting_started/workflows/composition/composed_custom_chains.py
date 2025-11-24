# Copyright (c) Microsoft. All rights reserved.

"""Compose two custom WorkflowBuilder connections with `connect` and stream outputs."""

import asyncio

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, WorkflowOutputEvent, handler


class Normalize(Executor):
    @handler
    async def normalize(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(text.strip().lower())


class Enrich(Executor):
    @handler
    async def enrich(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"{text} :: enriched")


class Summarize(Executor):
    @handler
    async def summarize(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"summary({text})")


class Publish(Executor):
    @handler
    async def publish(self, text: str, ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output(text)


async def main() -> None:
    normalize_connection = WorkflowBuilder().add_edge(Normalize(id="normalize"), Enrich(id="enrich")).set_start_executor(
        "normalize"
    )

    summarize_connection = WorkflowBuilder().add_edge(Summarize(id="summarize"), Publish(id="publish")).set_start_executor(
        "summarize"
    )

    builder = WorkflowBuilder()
    normalize_handle = builder.add_workflow(normalize_connection, prefix="prep")
    summarize_handle = builder.add_workflow(summarize_connection, prefix="summary")
    builder.connect(normalize_handle.outputs[0], summarize_handle.start)
    builder.set_start_executor(normalize_handle.start)

    workflow = builder.build()
    print("Outputs:")
    async for event in workflow.run_stream("  Hello Composition  "):
        if isinstance(event, WorkflowOutputEvent):
            print(event.data)

    """
    Sample output:

    Outputs:
    summary(hello composition :: enriched)
    """


if __name__ == "__main__":
    asyncio.run(main())
