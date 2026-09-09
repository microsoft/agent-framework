# Copyright (c) Microsoft. All rights reserved.

"""Tests for Workflow.resolve_pause_checkpoint_id / get_last_checkpoint_id."""

from typing import Any

import pytest

from agent_framework import (
    Content,
    Executor,
    InMemoryCheckpointStorage,
    WorkflowBuilder,
    WorkflowCheckpoint,
    WorkflowContext,
    handler,
    response_handler,
)


class _ApprovalExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="approval_executor")

    @handler
    async def start(self, message: Any, ctx: WorkflowContext) -> None:
        del message
        function_call = Content.from_function_call(
            call_id="refund-call",
            name="submit_refund",
            arguments={"order_id": "12345"},
        )
        approval_request = Content.from_function_approval_request(id="approval-1", function_call=function_call)
        await ctx.request_info(approval_request, Content, request_id="approval-1")

    @response_handler
    async def handle_approval(self, original_request: Content, response: Content, ctx: WorkflowContext) -> None:
        del original_request, response
        await ctx.yield_output("done")  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]


@pytest.mark.asyncio
async def test_resolve_pause_checkpoint_id_prefers_runner_over_shared_latest() -> None:
    storage = InMemoryCheckpointStorage()
    workflow = WorkflowBuilder(start_executor=_ApprovalExecutor(), checkpoint_storage=storage).build()
    baseline = workflow.get_last_checkpoint_id()

    async for _ in workflow.run("go", stream=True):
        pass

    pause_id = workflow.get_last_checkpoint_id()
    assert pause_id is not None
    assert pause_id != baseline

    competing = WorkflowCheckpoint(
        workflow_name=workflow.name,
        graph_signature_hash="competing",
        pending_request_info_events={},
        timestamp="9999-01-01T00:00:00+00:00",
    )
    await storage.save(competing)

    resolved = await workflow.resolve_pause_checkpoint_id(
        {"approval-1"},
        checkpoint_storage=storage,
        baseline_checkpoint_id=baseline,
    )
    assert resolved == pause_id


@pytest.mark.asyncio
async def test_resolve_pause_checkpoint_id_requires_run_scoped_change_without_storage() -> None:
    workflow = WorkflowBuilder(start_executor=_ApprovalExecutor()).build()
    workflow._runner._previous_checkpoint_id = "leftover"  # pyright: ignore[reportPrivateUsage]

    assert (
        await workflow.resolve_pause_checkpoint_id(
            {"approval-1"},
            baseline_checkpoint_id="leftover",
        )
        is None
    )
    assert (
        await workflow.resolve_pause_checkpoint_id(
            {"approval-1"},
            baseline_checkpoint_id=None,
        )
        == "leftover"
    )


@pytest.mark.asyncio
async def test_resolve_pause_checkpoint_id_uses_builder_storage() -> None:
    storage = InMemoryCheckpointStorage()
    workflow = WorkflowBuilder(start_executor=_ApprovalExecutor(), checkpoint_storage=storage).build()
    baseline = workflow.get_last_checkpoint_id()

    async for _ in workflow.run("go", stream=True):
        pass

    pause_id = workflow.get_last_checkpoint_id()
    resolved = await workflow.resolve_pause_checkpoint_id(
        {"approval-1"},
        baseline_checkpoint_id=baseline,
    )
    assert resolved == pause_id
