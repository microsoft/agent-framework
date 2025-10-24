# Copyright (c) Microsoft. All rights reserved.

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent_framework._workflows._checkpoint import WorkflowCheckpoint
from agent_framework._workflows._checkpoint_encoding import encode_checkpoint_value
from agent_framework._workflows._checkpoint_summary import get_checkpoint_summary
from agent_framework._workflows._const import EXECUTOR_STATE_KEY
from agent_framework._workflows._events import RequestInfoEvent, WorkflowEvent
from agent_framework._workflows._request_info_executor import (
    PendingRequestDetails,
    PendingRequestSnapshot,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
)
from agent_framework._workflows._runner_context import Message
from agent_framework._workflows._shared_state import SharedState
from agent_framework._workflows._workflow_context import WorkflowContext

PENDING_STATE_KEY = RequestInfoExecutor._PENDING_SHARED_STATE_KEY  # pyright: ignore[reportPrivateUsage]


class _StubRunnerContext:
    """Minimal runner context stub for exercising WorkflowContext helpers."""

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

    def has_checkpointing(self) -> bool:  # pragma: no cover - unused
        return False

    def set_workflow_id(self, workflow_id: str) -> None:  # pragma: no cover - unused
        pass

    def reset_for_new_run(self) -> None:  # pragma: no cover - unused
        pass

    async def create_checkpoint(
        self,
        shared_state: SharedState,
        iteration_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:  # pragma: no cover - unused
        raise RuntimeError("Checkpointing not supported in stub context")

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:  # pragma: no cover - unused
        return None

    async def apply_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:  # pragma: no cover - unused
        pass

    def set_streaming(self, streaming: bool) -> None:  # pragma: no cover - unused
        pass

    def is_streaming(self) -> bool:  # pragma: no cover - unused
        return False


@dataclass(kw_only=True)
class SimpleApproval(RequestInfoMessage):
    prompt: str = ""
    draft: str = ""
    iteration: int = 0


@dataclass(slots=True)
class SlottedApproval(RequestInfoMessage):
    note: str = ""


@dataclass
class TimedApproval(RequestInfoMessage):
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


async def test_rehydrate_falls_back_when_request_type_missing() -> None:
    """Rehydration should succeed even if the original request type cannot be imported.

    This simulates resuming a workflow where the HumanApprovalRequest class is unavailable
    in the current process (e.g., defined in __main__ during the original run).
    """
    request_id = "request-123"
    snapshot = PendingRequestSnapshot(
        request_id=request_id,
        source_executor_id="review_gateway",
        request_type="nonexistent.module:MissingRequest",
        request_as_json_safe_dict={
            "request_id": request_id,
        },
    )

    ctx: WorkflowContext[Any] = WorkflowContext("request_info", ["workflow"], SharedState(), _StubRunnerContext())
    await ctx.set_executor_state({PENDING_STATE_KEY: {request_id: snapshot}})

    executor = RequestInfoExecutor(id="request_info")

    event = await executor._rehydrate_request_event(request_id, ctx)  # pyright: ignore[reportPrivateUsage]

    assert event is not None
    assert event.request_id == request_id
    assert isinstance(event.data, RequestInfoMessage)


async def test_has_pending_request_detects_snapshot() -> None:
    request_id = "request-123"
    snapshot = PendingRequestSnapshot(
        request_id=request_id,
        source_executor_id="review_gateway",
        request_type="nonexistent.module:MissingRequest",
        request_as_json_safe_dict={
            "request_id": request_id,
        },
    )

    ctx: WorkflowContext[Any] = WorkflowContext("request_info", ["workflow"], SharedState(), _StubRunnerContext())
    await ctx.set_executor_state({PENDING_STATE_KEY: {request_id: snapshot}})

    executor = RequestInfoExecutor(id="request_info")

    assert await executor.has_pending_request(request_id, ctx)


async def test_has_pending_request_false_when_snapshot_absent() -> None:
    ctx: WorkflowContext[Any] = WorkflowContext("request_info", ["workflow"], SharedState(), _StubRunnerContext())
    await ctx.set_executor_state({PENDING_STATE_KEY: {}})

    executor = RequestInfoExecutor(id="request_info")

    assert not await executor.has_pending_request("missing", ctx)


def test_pending_requests_from_checkpoint_and_summary() -> None:
    request = SimpleApproval(prompt="Review draft", draft="Draft text", iteration=3)
    request.request_id = "req-42"

    response = RequestResponse[SimpleApproval, str](
        data="approve",
        original_request=request,
        request_id=request.request_id,
    )

    encoded_response = encode_checkpoint_value(response)

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
        iteration_count=1,
    )

    summary = get_checkpoint_summary(checkpoint)
    assert summary.checkpoint_id == "cp-1"
    assert summary.status == "awaiting request response"
    assert summary.pending_requests[0].request_id == "req-42"

    pending = summary.pending_requests
    assert len(pending) == 1
    entry = pending[0]
    assert isinstance(entry, PendingRequestDetails)
    assert entry.request_id == "req-42"
    assert entry.prompt == "Review draft"
    assert entry.draft == "Draft text"
    assert entry.iteration == 3
    assert entry.original_request is not None


def test_snapshot_state_serializes_non_json_payloads() -> None:
    executor = RequestInfoExecutor(id="request_info")

    timed = TimedApproval(issued_at=datetime(2024, 5, 4, 12, 30, 45))
    timed.request_id = "timed"
    slotted = SlottedApproval(note="slot-based")
    slotted.request_id = "slotted"

    executor._request_events = {  # pyright: ignore[reportPrivateUsage]
        timed.request_id: RequestInfoEvent(
            request_id=timed.request_id,
            source_executor_id="source",
            request_type=TimedApproval,
            request_data=timed,
        ),
        slotted.request_id: RequestInfoEvent(
            request_id=slotted.request_id,
            source_executor_id="source",
            request_type=SlottedApproval,
            request_data=slotted,
        ),
    }

    state = executor.snapshot_state()

    # Should be JSON serializable despite datetime/slots
    serialized = json.dumps(state)
    assert "timed" in serialized
    timed_payload = state["request_events"][timed.request_id]["request_data"]["value"]
    assert isinstance(timed_payload["issued_at"], str)


def test_restore_state_falls_back_to_base_request_type() -> None:
    executor = RequestInfoExecutor(id="request_info")

    approval = SimpleApproval(prompt="Review", draft="Draft", iteration=1)
    approval.request_id = "req"
    executor._request_events = {  # pyright: ignore[reportPrivateUsage]
        approval.request_id: RequestInfoEvent(
            request_id=approval.request_id,
            source_executor_id="source",
            request_type=SimpleApproval,
            request_data=approval,
        )
    }

    state = executor.snapshot_state()
    state["request_events"][approval.request_id]["request_type"] = "missing.module:GhostRequest"

    executor.restore_state(state)

    restored = executor._request_events[approval.request_id]  # pyright: ignore[reportPrivateUsage]
    assert restored.request_type is RequestInfoMessage
    assert isinstance(restored.data, RequestInfoMessage)


async def test_run_persists_pending_requests_in_runner_state() -> None:
    shared_state = SharedState()
    runner_ctx = _StubRunnerContext()
    ctx: WorkflowContext[None] = WorkflowContext("request_info", ["source"], shared_state, runner_ctx)

    executor = RequestInfoExecutor(id="request_info")
    approval = SimpleApproval(prompt="Review", draft="Draft", iteration=1)
    approval.request_id = "req-123"

    await executor.execute(approval, ctx.source_executor_ids, shared_state, runner_ctx)

    # Runner state should include both pending snapshot and serialized request events
    assert await shared_state.has(EXECUTOR_STATE_KEY)
    executor_state = await shared_state.get(EXECUTOR_STATE_KEY)
    assert executor.id in executor_state
    assert PENDING_STATE_KEY in executor_state[executor.id]
    assert approval.request_id in executor_state[executor.id][PENDING_STATE_KEY]

    response_ctx: WorkflowContext[None] = WorkflowContext("request_info", ["source"], shared_state, runner_ctx)
    await executor.handle_response("approved", approval.request_id, response_ctx)  # type: ignore

    assert executor_state[executor.id][PENDING_STATE_KEY] == {}
