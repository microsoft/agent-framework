# Copyright (c) Microsoft. All rights reserved.

"""Demonstrates composing Sequential and Concurrent builders with `connect`."""

import asyncio
from typing import cast

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunResponse,
    ChatMessage,
    ConcurrentBuilder,
    Executor,
    Role,
    SequentialBuilder,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    handler,
)


class DraftExecutor(Executor):
    @handler
    async def draft(self, conversation: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        updated = list(conversation)
        updated.append(ChatMessage(role=Role.ASSISTANT, text="Drafted response"))
        await ctx.send_message(updated)


class RefineExecutor(Executor):
    @handler
    async def refine(self, conversation: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        updated = list(conversation)
        updated.append(ChatMessage(role=Role.ASSISTANT, text="Refined draft"))
        await ctx.send_message(updated)


class ReviewWorker(Executor):
    @handler
    async def review(
        self,
        request: AgentExecutorRequest,
        ctx: WorkflowContext[AgentExecutorResponse],
    ) -> None:
        latest = request.messages[-1].text if request.messages else ""
        reply = ChatMessage(role=Role.ASSISTANT, text=f"{self.id} reviewed: {latest}")
        await ctx.send_message(
            AgentExecutorResponse(
                executor_id=self.id,
                agent_run_response=AgentRunResponse(messages=[reply]),
                full_conversation=list(request.messages) + [reply],
            )
        )


class Aggregator(Executor):
    @handler
    async def combine(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        combined: list[ChatMessage] = []
        for result in results:
            combined.extend(result.full_conversation or [])
        await ctx.send_message(combined)


class Emit(Executor):
    @handler
    async def emit(
        self, conversation: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage], list[ChatMessage]]
    ) -> None:
        await ctx.yield_output(conversation)


async def main() -> None:
    sequential_fragment = (
        SequentialBuilder().participants([DraftExecutor(id="draft"), RefineExecutor(id="refine")]).as_connection()
    )

    concurrent_fragment = (
        ConcurrentBuilder()
        .participants([ReviewWorker(id="legal"), ReviewWorker(id="brand")])
        .with_aggregator(Aggregator(id="collect"))
        .as_connection()
    )

    builder = WorkflowBuilder()
    seq_handle = builder.add_connection(sequential_fragment, prefix="seq")
    concurrent_handle = builder.add_connection(concurrent_fragment, prefix="conc")

    # Wire sequential output into concurrent, then terminate with emit:
    # - sequential fragment outputs a list[ChatMessage] conversation -> feed into concurrent start
    # - concurrent aggregator emits list[ChatMessage] results -> send to emit to yield workflow output
    builder.connect(seq_handle.output_points[0], concurrent_handle.start_id)
    builder.connect(concurrent_handle.output_points[0], Emit(id="emit"))
    builder.set_start_executor(seq_handle.start_id)

    workflow = builder.build()
    print("Outputs:")
    async for event in workflow.run_stream("Start"):
        if isinstance(event, WorkflowOutputEvent):
            msgs = cast(list[ChatMessage], event.data)
            for message in msgs:
                print(f"- {message.role.value}: {message.text}")

    """
    Sample Output:

    Outputs:
    - user: Start
    - assistant: Drafted response
    - assistant: Refined draft
    - user: Start
    - assistant: Drafted response
    - assistant: Refined draft
    - assistant: conc/legal reviewed: Refined draft
    - user: Start
    - assistant: Drafted response
    - assistant: Refined draft
    - assistant: conc/brand reviewed: Refined draft
    """


if __name__ == "__main__":
    asyncio.run(main())
