# Copyright (c) Microsoft. All rights reserved.

"""Connect a custom workflow fragment into a concurrent pattern."""

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
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    handler,
)


class Intake(Executor):
    @handler
    async def accept(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"INTAKE: {text}")


class Screen(Executor):
    @handler
    async def screen(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"{text} [SCREENED]")


class ReviewWorker(Executor):
    @handler
    async def review(
        self,
        request: AgentExecutorRequest,
        ctx: WorkflowContext[AgentExecutorResponse],
    ) -> None:
        latest = request.messages[-1].text if request.messages else ""
        reply = ChatMessage(role=Role.ASSISTANT, text=f"{self.id} approval: {latest}")
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
    intake_fragment = WorkflowBuilder().add_edge(Intake(id="intake"), Screen(id="screen")).set_start_executor("intake")

    concurrent_fragment = (
        ConcurrentBuilder()
        .participants([ReviewWorker(id="policy"), ReviewWorker(id="risk")])
        .with_aggregator(Aggregator(id="combine"))
    )

    builder = WorkflowBuilder()
    intake_handle = builder.add_workflow(intake_fragment, prefix="intake")
    concurrent_handle = builder.add_workflow(concurrent_fragment, prefix="review")
    builder.connect(intake_handle.outputs[0], concurrent_handle.start)
    builder.connect(concurrent_handle.outputs[0], Emit(id="emit"))
    builder.set_start_executor(intake_handle.start)

    workflow = builder.build()
    print("Outputs:")
    async for event in workflow.run_stream("Order 123"):
        if isinstance(event, WorkflowOutputEvent):
            msgs = cast(list[ChatMessage], event.data)
            for message in msgs:
                print(f"- {message.role.value}: {message.text}")

    """
    Sample Output:

    Outputs:
    - user: INTAKE: Order 123 [SCREENED]
    - assistant: review/policy approval: INTAKE: Order 123 [SCREENED]
    - user: INTAKE: Order 123 [SCREENED]
    - assistant: review/risk approval: INTAKE: Order 123 [SCREENED]
    """


if __name__ == "__main__":
    asyncio.run(main())
