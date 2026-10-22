# /// script
# dependencies = ["agent-framework-foundry-hosting", "pydantic"]
# ///
# Copyright (c) Microsoft. All rights reserved.

"""Run a typed native countdown with exact stored background output/checkpoint recovery."""

import asyncio

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler
from agent_framework_foundry_hosting import (
    CheckpointStoreProvider,
    HostedResponseRequest,
    ResponsesHostServer,
    WorkflowTurn,
)
from azure.ai.agentserver.core.tasks import set_resilient_tasks_enabled
from azure.ai.agentserver.responses import ResponsesServerOptions
from pydantic import BaseModel, Field


class CountdownRequest(BaseModel):
    target: int = Field(ge=0)
    label: str = "countdown"


class StartExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="start")

    @handler
    async def start(self, request: CountdownRequest, ctx: WorkflowContext[int, str]) -> None:
        ctx.set_state("label", request.label)
        await ctx.send_message(request.target)


class CountdownExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="countdown")

    @handler
    async def countdown(self, target: int, ctx: WorkflowContext[int, str]) -> None:
        if target == 0:
            await ctx.yield_output(f"{ctx.get_state('label')} complete.")
            return
        await asyncio.sleep(1)
        await ctx.yield_output(str(target))
        await ctx.send_message(target - 1, target_id=self.id)


def build_workflow(request: HostedResponseRequest) -> Workflow:
    """Return freshly built executors with stable IDs for every invocation and recovery."""
    start, countdown = StartExecutor(), CountdownExecutor()
    return (
        WorkflowBuilder(name="countdown-workflow-v1", start_executor=start)
        .add_edge(start, countdown)
        .add_edge(countdown, countdown)
        .build()
    )


async def parse_response(request: HostedResponseRequest) -> WorkflowTurn[CountdownRequest]:
    return WorkflowTurn(input=CountdownRequest.model_validate_json(await request.get_input_text() or ""))


def main() -> None:
    # The application's explicit SDK task opt-in is separate from output checkpointing.
    set_resilient_tasks_enabled(True)
    ResponsesHostServer(
        workflow=build_workflow,
        parse_response=parse_response,
        checkpoint_store_provider=CheckpointStoreProvider(
            allowed_checkpoint_types=[f"{CountdownRequest.__module__}:{CountdownRequest.__qualname__}"],
        ),
        options=ResponsesServerOptions(resilient_background=True),
    ).run()


if __name__ == "__main__":
    main()
