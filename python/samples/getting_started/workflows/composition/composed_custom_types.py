# Copyright (c) Microsoft. All rights reserved.

"""Demonstrates connecting typed workflow segments with custom data models."""

import asyncio
from dataclasses import dataclass

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, WorkflowOutputEvent, handler


@dataclass
class Task:
    id: str
    text: str


@dataclass
class EnrichedTask:
    id: str
    text: str
    tags: list[str]


@dataclass
class Decision:
    id: str
    approved: bool
    reason: str


class Ingest(Executor):
    @handler
    async def create(self, text: str, ctx: WorkflowContext[Task]) -> None:
        await ctx.send_message(Task(id="t1", text=text))


class Tagger(Executor):
    @handler
    async def tag(self, task: Task, ctx: WorkflowContext[EnrichedTask]) -> None:
        tags = ["long"] if len(task.text) > 10 else ["short"]
        await ctx.send_message(EnrichedTask(id=task.id, text=task.text, tags=tags))


class Reviewer(Executor):
    @handler
    async def review(self, enriched: EnrichedTask, ctx: WorkflowContext[Decision]) -> None:
        approved = "short" in enriched.tags
        reason = "auto-approve short tasks" if approved else "needs manual review"
        await ctx.send_message(Decision(id=enriched.id, approved=approved, reason=reason))


class Publish(Executor):
    @handler
    async def publish(self, decision: Decision, ctx: WorkflowContext[Decision, Decision]) -> None:
        await ctx.yield_output(decision)


async def main() -> None:
    # Connection A: string -> Task -> EnrichedTask
    prep = (
        WorkflowBuilder()
        .add_edge(Ingest(id="ingest"), Tagger(id="tagger"))
        .set_start_executor("ingest")
        .as_connection()
    )

    # Connection B: EnrichedTask -> Decision -> publish
    review = (
        WorkflowBuilder()
        .add_edge(Reviewer(id="reviewer"), Publish(id="publish"))
        .set_start_executor("reviewer")
        .as_connection()
    )

    builder = WorkflowBuilder()
    prep_handle = builder.add_connection(prep, prefix="prep")
    review_handle = builder.add_connection(review, prefix="rev")

    # Wire using typed connection points (no raw ids):
    # - prep_handle.output_points[0] describes the exit executor AND its output types (EnrichedTask here)
    # - review_handle.start_id refers to the entry executor whose input types include EnrichedTask
    builder.connect(prep_handle.output_points[0], review_handle.start_id)
    builder.set_start_executor(prep_handle.start_id)

    workflow = builder.build()
    print("Outputs:")
    async for event in workflow.run_stream("Process this short task"):
        if isinstance(event, WorkflowOutputEvent):
            decision = event.data
            print(decision)

    """
    Sample Output:

    Outputs:
    Decision(id='t1', approved=False, reason='needs manual review')
    """


if __name__ == "__main__":
    asyncio.run(main())
