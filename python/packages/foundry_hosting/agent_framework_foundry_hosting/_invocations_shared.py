# Copyright (c) Microsoft. All rights reserved.

"""Share Invocations identity, wire conversion, and streaming cleanup helpers."""

from __future__ import annotations

import json
import math
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any, cast

from agent_framework import AgentResponse, AgentResponseUpdate, ChatResponse, ChatResponseUpdate, WorkflowEvent
from anyio import CancelScope
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext, get_request_context
from azure.ai.agentserver.core.storage import FoundryStorageConflictError, FoundryStoragePreconditionError
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from ._scope import FoundryRequestScope
from ._shared import WorkflowBlockedError, WorkflowConflictError


def invocation_partition_key(
    config: AgentConfig,
    *,
    context: FoundryAgentRequestContext | None = None,
    scope: FoundryRequestScope | None = None,
) -> str | tuple[str, str]:
    """Resolve the session key, preserving hosted session/user boundaries."""
    if context is None:
        context = get_request_context()

    if config.is_hosted:
        if not context.user_id:
            raise RuntimeError(
                "The hosted environment is missing user_id in the request context. "
                "Please ensure that the request is coming from a valid Foundry platform service."
            )
        hosted_scope = scope or FoundryRequestScope.from_context(config, context)
        return hosted_scope.session_id, context.user_id

    if not context.session_id:
        raise RuntimeError(
            "The request context is missing session_id. Please ensure that the request is a valid request."
        )
    return context.session_id


def invocation_request_scope(
    config: AgentConfig, request: Request, context: FoundryAgentRequestContext
) -> FoundryRequestScope | None:
    """Resolve hosted identity, requiring a routed query when the platform session is unconfigured."""
    if not config.is_hosted:
        return None
    if not context.user_id:
        raise RuntimeError("The hosted environment is missing user_id in the request context.")

    routed_session_ids = request.query_params.getlist("agent_session_id")
    if len(routed_session_ids) > 1:
        raise RuntimeError("Hosted Invocations requires exactly one agent_session_id query parameter.")
    routed_session_id = routed_session_ids[0] if routed_session_ids else None
    if config.session_id:
        if routed_session_id is not None and routed_session_id != config.session_id:
            raise RuntimeError("The request agent_session_id does not match the platform session ID.")
        return FoundryRequestScope.from_context(config, context)

    if not routed_session_id or routed_session_id != context.session_id:
        raise RuntimeError(
            "Hosted Invocations without FOUNDRY_AGENT_SESSION_ID require an explicit routed "
            "agent_session_id query parameter matching the request context."
        )
    if not context.call_id:
        raise RuntimeError("Foundry hosted requests require a trusted user ID and call ID.")
    return FoundryRequestScope(
        session_id=routed_session_id,
        user_id=context.user_id,
        call_id=context.call_id,
        is_hosted=True,
    )


class _WorkflowOutputError(TypeError):
    """Workflow application data cannot be represented as JSON."""


class _WorkflowRequestError(ValueError):
    """A validated application request cannot be dispatched to the workflow."""


def _validate_workflow_mapping_keys(value: Any, path: str, active: set[int]) -> None:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, Any], value)
        identifier = id(mapping)
        if identifier in active:
            raise _WorkflowOutputError(f"Workflow output at {path} is not JSON-serializable: circular mapping.")
        active.add(identifier)
        try:
            for index, (key, item) in enumerate(mapping.items()):
                if not isinstance(key, str):
                    raise _WorkflowOutputError(
                        f"Workflow output at {path} is not JSON-serializable: "
                        f"mapping keys must be strings, found {type(key).__name__}."
                    )
                _validate_workflow_mapping_keys(item, f"{path}.value[{index}]", active)
        finally:
            active.remove(identifier)
    elif isinstance(value, (list, tuple)):
        sequence = cast(Sequence[Any], value)
        identifier = id(sequence)
        if identifier in active:
            raise _WorkflowOutputError(f"Workflow output at {path} is not JSON-serializable: circular sequence.")
        active.add(identifier)
        try:
            for index, item in enumerate(sequence):
                _validate_workflow_mapping_keys(item, f"{path}[{index}]", active)
        finally:
            active.remove(identifier)


def _workflow_serialized_value(value: Any, path: str) -> Any:
    if isinstance(value, (AgentResponse, AgentResponseUpdate, ChatResponse, ChatResponseUpdate)):
        return value.to_dict(exclude={"continuation_token"})
    if isinstance(value, BaseModel):
        _validate_workflow_mapping_keys(value.model_dump(mode="python"), f"{path}.model", set())
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise _WorkflowOutputError(
        f"Workflow output at {path} is not JSON-serializable: unsupported type {type(value).__name__}."
    )


def _workflow_json_value(value: Any, path: str, active: set[int]) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _WorkflowOutputError(f"Workflow output at {path} is not JSON-serializable: number must be finite.")
        return value
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, Any], value)
        identifier = id(mapping)
        if identifier in active:
            raise _WorkflowOutputError(f"Workflow output at {path} is not JSON-serializable: circular mapping.")
        active.add(identifier)
        try:
            result: dict[str, Any] = {}
            for index, (key, item) in enumerate(mapping.items()):
                if not isinstance(key, str):
                    raise _WorkflowOutputError(
                        f"Workflow output at {path} is not JSON-serializable: "
                        f"mapping keys must be strings, found {type(key).__name__}."
                    )
                result[key] = _workflow_json_value(item, f"{path}.value[{index}]", active)
            return result
        finally:
            active.remove(identifier)
    if isinstance(value, (list, tuple)):
        sequence = cast(Sequence[Any], value)
        identifier = id(sequence)
        if identifier in active:
            raise _WorkflowOutputError(f"Workflow output at {path} is not JSON-serializable: circular sequence.")
        active.add(identifier)
        try:
            return [_workflow_json_value(item, f"{path}[{index}]", active) for index, item in enumerate(sequence)]
        finally:
            active.remove(identifier)
    identifier = id(value)
    if identifier in active:
        raise _WorkflowOutputError(f"Workflow output at {path} is not JSON-serializable: circular serialized value.")
    active.add(identifier)
    try:
        serialized = _workflow_serialized_value(value, path)
        return _workflow_json_value(serialized, f"{path}.serialized", active)
    finally:
        active.remove(identifier)


def _workflow_output(value: Any) -> Any:
    """Normalize typed application data without text coercion or skipped values."""
    try:
        normalized = _workflow_json_value(value, "$", set())
        return json.loads(json.dumps(normalized, allow_nan=False, ensure_ascii=False).encode("utf-8"))
    except _WorkflowOutputError:
        raise
    except (TypeError, ValueError, RecursionError) as exc:
        raise _WorkflowOutputError(f"Workflow output type {type(value).__name__} is not JSON-serializable.") from exc


def _workflow_frame(  # pyright: ignore[reportUnusedFunction]
    event: WorkflowEvent[Any],
) -> dict[str, Any] | None:
    if event.type not in ("output", "request_info"):
        return None
    frame: dict[str, Any] = {"type": event.type, "data": event.data}
    if event.type == "request_info":
        frame["request_id"] = event.request_id
        frame["source_executor_id"] = event.source_executor_id
    else:
        frame["executor_id"] = event.executor_id
    return cast(dict[str, Any], _workflow_output(frame))


def _workflow_snapshot_frames(  # pyright: ignore[reportUnusedFunction]
    snapshot: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if snapshot is None or set(snapshot) != {"output"} or not isinstance(snapshot["output"], list):
        raise RuntimeError("The stored Invocations workflow output snapshot is invalid.")
    frames: list[dict[str, Any]] = []
    for item in cast(list[Any], snapshot["output"]):
        if not isinstance(item, Mapping):
            raise RuntimeError("The stored Invocations workflow output snapshot is invalid.")
        frame = cast(dict[str, Any], _workflow_output(item))
        if frame.get("type") == "output":
            if set(frame) != {"type", "data", "executor_id"}:
                raise RuntimeError("The stored Invocations workflow output snapshot is invalid.")
        elif frame.get("type") == "request_info":
            if set(frame) != {"type", "data", "request_id", "source_executor_id"}:
                raise RuntimeError("The stored Invocations workflow output snapshot is invalid.")
        else:
            raise RuntimeError("The stored Invocations workflow output snapshot is invalid.")
        frames.append(frame)
    return frames


def _workflow_frame_size(  # pyright: ignore[reportUnusedFunction]
    frame: Mapping[str, Any],
) -> int:
    return len(json.dumps(frame, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))


def _sse(  # pyright: ignore[reportUnusedFunction]
    event: str, data: Mapping[str, Any]
) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _invocation_failure(exc: Exception) -> tuple[str, int, str]:
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, (FoundryStorageConflictError, FoundryStoragePreconditionError)):
            return "Another request advanced this agent session; reload before retrying.", 409, "session_conflict"
        cause = cause.__cause__
    return "Agent invocation failed.", 500, "invocation_failed"


def _workflow_failure(  # pyright: ignore[reportUnusedFunction]
    exc: Exception,
) -> tuple[str, int, str]:
    if isinstance(exc, _WorkflowOutputError):
        return str(exc), 500, "invalid_workflow_output"
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, WorkflowBlockedError):
            return (
                "This workflow turn was interrupted or failed; start a new Foundry sandbox.",
                409,
                "workflow_blocked",
            )
        if isinstance(cause, WorkflowConflictError):
            return str(cause), 409, "workflow_conflict"
        cause = cause.__cause__
    if _invocation_failure(exc)[1] == 409:
        return "Another request advanced this workflow; reload before retrying.", 409, "workflow_conflict"
    if isinstance(exc, _WorkflowRequestError):
        return str(exc), 400, "invalid_workflow_turn"
    if isinstance(exc, PermissionError):
        return "Workflow state is not available in this trusted scope.", 403, "workflow_scope"
    return "Workflow invocation failed.", 500, "workflow_invocation_failed"


class _InvocationStreamingResponse(StreamingResponse):
    def __init__(self, content: AsyncGenerator[str]) -> None:
        super().__init__(
            content,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
        self._content = content

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # The SDK may wrap the iterator in a keep-alive pump; join it before closing its source.
            try:
                close = getattr(self.body_iterator, "aclose", None)
                if close is not None:
                    await close()
            finally:
                if self.body_iterator is not self._content:
                    await self._content.aclose()


class _WorkflowStreamingResponse(_InvocationStreamingResponse):  # pyright: ignore[reportUnusedClass]
    def __init__(self, content: AsyncGenerator[str], *, keep_alive: bool) -> None:
        super().__init__(content)
        self._keep_alive = keep_alive

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            with CancelScope(shield=True):
                if self._keep_alive and self.body_iterator is not self._content:
                    close = getattr(self.body_iterator, "aclose", None)
                    if close is None:
                        raise TypeError("The Invocations SDK stream iterator must support aclose.")
                    await close()
                try:
                    await self._content.aclose()
                finally:
                    # Without the SDK pump, finish its wrapper in the task that created its context tokens.
                    async for _ in self.body_iterator:
                        pass
