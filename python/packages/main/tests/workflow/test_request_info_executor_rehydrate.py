# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any

import pytest

from agent_framework._workflow._checkpoint import WorkflowCheckpoint
from agent_framework._workflow._events import WorkflowEvent
from agent_framework._workflow._executor import (
    PendingRequestDetails,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
)
from agent_framework._workflow._runner_context import CheckpointState, Message, _encode_checkpoint_value  # type: ignore
from agent_framework._workflow._shared_state import SharedState
from agent_framework._workflow._workflow_context import WorkflowContext

PENDING_STATE_KEY = RequestInfoExecutor._PENDING_SHARED_STATE_KEY  # pyright: ignore[reportPrivateUsage]


class _StubRunnerContext:
    """Minimal runner context stub for exercising WorkflowContext helpers."""

    def __init__(self, stored_state: dict[str, Any] | None = None) -> None:
        self._state = stored_state or {}

    async def send_message(self, message: Message) -> None:  # pragma: no cover - unused in tests
        return None

    async def drain_messages(self) -> dict[str, list[Message]]:  # pragma: no cover - unused
        return {}

    async def has_messages(self) -> bool:  # pragma: no cover - unused
        return False

    async def add_event(self, event: WorkflowEvent) -> None:  # pragma: no cover - unused
        return None

    async def drain_events(self) -> list[WorkflowEvent]:  # pragma: no cover - unused
        return []

    async def has_events(self) -> bool:  # pragma: no cover - unused
        return False

    async def next_event(self) -> WorkflowEvent:  # pragma: no cover - unused
        raise RuntimeError("Not implemented in stub context")

    async def get_state(self, executor_id: str) -> dict[str, Any] | None:  # pragma: no cover - trivial
        return self._state

    async def set_state(self, executor_id: str, state: dict[str, Any]) -> None:  # pragma: no cover - unused
        self._state = state

    def has_checkpointing(self) -> bool:  # pragma: no cover - unused
        return False

    def set_workflow_id(self, workflow_id: str) -> None:  # pragma: no cover - unused
        pass

    def reset_for_new_run(self, workflow_shared_state: SharedState | None = None) -> None:  # pragma: no cover - unused
        pass

    async def create_checkpoint(self, metadata: dict[str, Any] | None = None) -> str:  # pragma: no cover - unused
        raise RuntimeError("Checkpointing not supported in stub context")

    async def restore_from_checkpoint(self, checkpoint_id: str) -> bool:  # pragma: no cover - unused
        return False

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:  # pragma: no cover - unused
        return None

    async def get_checkpoint_state(self) -> CheckpointState:  # pragma: no cover - unused
        return {}  # type: ignore[return-value]

    async def set_checkpoint_state(self, state: CheckpointState) -> None:  # pragma: no cover - unused
        pass


@dataclass(kw_only=True)
class SimpleApproval(RequestInfoMessage):
    prompt: str = ""
    draft: str = ""
    iteration: int = 0


@pytest.mark.asyncio
async def test_rehydrate_falls_back_when_request_type_missing() -> None:
    """Rehydration should succeed even if the original request type cannot be imported.

    This simulates resuming a workflow where the HumanApprovalRequest class is unavailable
    in the current process (e.g., defined in __main__ during the original run).
    """

    request_id = "request-123"
    snapshot = {
        "request_id": request_id,
        "source_executor_id": "review_gateway",
        "request_type": "nonexistent.module:MissingRequest",
        "summary": "...",
        "details": {
            "request_id": request_id,
            "prompt": "Review draft",
            "draft": "Draft text",
            "iteration": 2,
        },
    }

    shared_state = SharedState()
    async with shared_state.hold():
        await shared_state.set_within_hold(
            PENDING_STATE_KEY,
            {request_id: snapshot},
        )

    runner_ctx = _StubRunnerContext({"pending_requests": {request_id: snapshot}})
    ctx: WorkflowContext[Any] = WorkflowContext("request_info", ["workflow"], shared_state, runner_ctx)

    executor = RequestInfoExecutor(id="request_info")

    event = await executor._rehydrate_request_event(request_id, ctx)  # pyright: ignore[reportPrivateUsage]

    assert event is not None
    assert event.request_id == request_id
    assert isinstance(event.data, RequestInfoMessage)
    assert getattr(event.data, "prompt", None) == "Review draft"
    assert getattr(event.data, "iteration", None) == 2


@pytest.mark.asyncio
async def test_has_pending_request_detects_snapshot() -> None:
    request_id = "req-pending"
    snapshot = {
        "request_id": request_id,
        "source_executor_id": "review_gateway",
        "details": {
            "request_id": request_id,
            "prompt": "Review",
            "draft": "Draft",
        },
    }

    shared_state = SharedState()
    async with shared_state.hold():
        await shared_state.set_within_hold(
            PENDING_STATE_KEY,
            {request_id: snapshot},
        )

    runner_ctx = _StubRunnerContext({"pending_requests": {request_id: snapshot}})
    ctx: WorkflowContext[Any] = WorkflowContext("request_info", ["workflow"], shared_state, runner_ctx)

    executor = RequestInfoExecutor(id="request_info")

    assert await executor.has_pending_request(request_id, ctx)


@pytest.mark.asyncio
async def test_has_pending_request_false_when_snapshot_absent() -> None:
    shared_state = SharedState()
    runner_ctx = _StubRunnerContext({"pending_requests": {}})
    ctx: WorkflowContext[Any] = WorkflowContext("request_info", ["workflow"], shared_state, runner_ctx)

    executor = RequestInfoExecutor(id="request_info")

    assert not await executor.has_pending_request("missing", ctx)


def test_pending_requests_from_checkpoint_and_summary() -> None:
    request = SimpleApproval(prompt="Review draft", draft="Draft text", iteration=3)
    request.request_id = "req-42"

    response = RequestResponse[SimpleApproval, str].handled("approve")
    response = RequestResponse[SimpleApproval, str].with_correlation(
        response,
        request,
        request.request_id,
    )

    encoded_response = _encode_checkpoint_value(response)

    checkpoint = WorkflowCheckpoint(
        checkpoint_id="cp-1",
        workflow_id="wf",
        messages={
            "request_info": [
                {
                    "data": encoded_response,
                    "source_id": "request_info",
                    "target_id": "review_gateway",
                }
            ]
        },
        shared_state={
            PENDING_STATE_KEY: {
                request.request_id: {
                    "request_id": request.request_id,
                    "prompt": request.prompt,
                    "draft": request.draft,
                    "iteration": request.iteration,
                    "source_executor_id": "review_gateway",
                }
            }
        },
        executor_states={},
        iteration_count=1,
    )

    pending = RequestInfoExecutor.pending_requests_from_checkpoint(checkpoint)
    assert len(pending) == 1
    entry = pending[0]
    assert isinstance(entry, PendingRequestDetails)
    assert entry.request_id == "req-42"
    assert entry.prompt == "Review draft"
    assert entry.draft == "Draft text"
    assert entry.iteration == 3
    assert entry.original_request is not None

    summary = RequestInfoExecutor.checkpoint_summary(checkpoint)
    assert summary.checkpoint_id == "cp-1"
    assert summary.status == "awaiting human response"
    assert summary.pending_requests[0].request_id == "req-42"
