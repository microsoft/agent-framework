# Copyright (c) Microsoft. All rights reserved.

"""Host checkpoint-owned native workflows through the Invocations protocol."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import math
import sys
import uuid
import weakref
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from contextvars import Token
from dataclasses import asdict, is_dataclass
from typing import Any, cast

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    ChatResponse,
    ChatResponseUpdate,
    CheckpointStorage,
    WorkflowCheckpointException,
    WorkflowEvent,
)
from agent_framework._telemetry import mark_feature_used
from anyio import CancelScope
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    get_request_context,
    reset_request_context,
    set_request_context,
)
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import Send

from ._feature_usage import FeatureIndex
from ._invocations_shared import (
    InvocationStreamingResponse,
    hosted_scope,
    invocation_failure,
    partition_key,
    sse_frame,
)
from ._scope import FoundryRequestScope
from ._shared import WorkflowResolver, WorkflowSource, WorkflowTurn, validate_sse_keep_alive_interval, workflow_agents
from ._state_store import CheckpointStoreProvider, ContextScopedStoreProvider
from ._workflow_state import HostedWorkflowRun, WorkflowBlockedError, WorkflowConflictError

logger = logging.getLogger(__name__)

WorkflowParser = Callable[[Request], WorkflowTurn[Any] | Awaitable[WorkflowTurn[Any]]]

_MAX_WORKFLOW_SNAPSHOT_EVENTS = 4096
_MAX_WORKFLOW_SNAPSHOT_BYTES = 4 * 1024 * 1024


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


def _workflow_frame(event: WorkflowEvent[Any]) -> dict[str, Any] | None:
    if event.type not in ("output", "request_info"):
        return None
    frame: dict[str, Any] = {"type": event.type, "data": event.data}
    if event.type == "request_info":
        frame["request_id"] = event.request_id
        frame["source_executor_id"] = event.source_executor_id
    else:
        frame["executor_id"] = event.executor_id
    return cast(dict[str, Any], _workflow_output(frame))


def _workflow_snapshot_frames(snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
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


def _workflow_frame_size(frame: Mapping[str, Any]) -> int:
    return len(json.dumps(frame, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))


def _workflow_failure(exc: Exception) -> tuple[str, int, str]:
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
    if invocation_failure(exc)[1] == 409:
        return "Another request advanced this workflow; reload before retrying.", 409, "workflow_conflict"
    if isinstance(exc, _WorkflowRequestError):
        return str(exc), 400, "invalid_workflow_turn"
    if isinstance(exc, PermissionError):
        return "Workflow state is not available in this trusted scope.", 403, "workflow_scope"
    return "Workflow invocation failed.", 500, "workflow_invocation_failed"


class _WorkflowStreamingResponse(InvocationStreamingResponse):
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


class InvocationsWorkflowHostServer(InvocationAgentServerHost):
    """Host a native, checkpoint-owned workflow with application-defined Invocations turns."""

    def __init__(
        self,
        workflow: WorkflowSource[Request],
        *,
        parse_input: WorkflowParser,
        openapi_spec: dict[str, Any] | None = None,
        checkpoint_store_provider: ContextScopedStoreProvider[CheckpointStorage] | None = None,
        sse_keep_alive_interval_seconds: int | None = None,
        **agent_server_kwargs: Any,
    ) -> None:
        """Create a native workflow host with explicit parsing and checkpoint ownership.

        Args:
            workflow: Sync or async request-aware factory, called for each request. Build fresh workflows,
                executors, agents, clients, providers, and mutable tools inside the factory. Keep workflow
                and executor IDs stable for checkpoint restoration. The host enters and closes context-managed
                agents; applications own other resource cleanup. Known shared execution resources are rejected.

        Keyword Args:
            parse_input: Required sync or async parser returning typed `WorkflowTurn` input or a complete
                pending reply batch. The parser validates the request and explicitly supplies any workflow
                kwargs; the host never converts the request body on its own.
            openapi_spec: Application OpenAPI specification forwarded to AgentServer.
            checkpoint_store_provider: Scoped checkpoint storage. Defaults to `CheckpointStoreProvider`.
                Native workflow history and pending replies are checkpoint-owned.
            sse_keep_alive_interval_seconds: Positive streaming heartbeat interval. If omitted, use a positive
                `SSE_KEEPALIVE_INTERVAL`, otherwise disable heartbeats. Not a request/model timeout.
            **agent_server_kwargs: Additional AgentServer SDK constructor arguments, such as
                `asyncapi_spec_json` and `asyncapi_spec_yaml`. Output uses JSON or framed SSE workflow events.

        Raises:
            TypeError: If the workflow is not a request-aware factory, the parser is not callable, or the
                heartbeat type is invalid.
            ValueError: If the heartbeat interval is nonpositive.
        """
        if not callable(parse_input):
            raise TypeError("parse_input must be a callable returning WorkflowTurn.")
        validate_sse_keep_alive_interval(sse_keep_alive_interval_seconds)
        self._workflow_resolver: WorkflowResolver[Request] = WorkflowResolver(workflow)
        super().__init__(openapi_spec=openapi_spec, **agent_server_kwargs)
        if sse_keep_alive_interval_seconds is not None:
            self.config.sse_keepalive_interval = sse_keep_alive_interval_seconds
        self._parse_input = parse_input
        self._checkpoint_storage_provider = (
            CheckpointStoreProvider() if checkpoint_store_provider is None else checkpoint_store_provider
        )
        self._session_locks: weakref.WeakValueDictionary[str | tuple[str, str], asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self.invoke_handler(self._handle_invoke)
        mark_feature_used(FeatureIndex.FOUNDRY_HOSTING)

    async def _parse(self, request: Request) -> WorkflowTurn[Any]:
        result = self._parse_input(request)
        parsed = await result if inspect.isawaitable(result) else result
        if not isinstance(parsed, WorkflowTurn):
            raise TypeError("parse_input must return WorkflowTurn.")
        return parsed

    async def _handle_invoke(self, request: Request) -> Response:
        """Run the native workflow for one trusted request."""
        context = get_request_context()
        try:
            scope = hosted_scope(self.config, request, context) if self.config.is_hosted else None
            key = partition_key(self.config, context, scope)
        except RuntimeError as exc:
            logger.error("Failed to resolve Invocations session: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

        try:
            turn = await self._parse(request)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception:
            logger.exception("Failed to prepare Invocations request")
            return JSONResponse({"error": "Failed to prepare invocation request."}, status_code=500)

        return await self._handle_workflow(
            request, turn, scope or FoundryRequestScope.from_context(self.config, context), context, key
        )

    async def _handle_workflow(
        self,
        request: Request,
        turn: WorkflowTurn[Any],
        scope: FoundryRequestScope,
        context: FoundryAgentRequestContext,
        partition_key: str | tuple[str, str],
    ) -> Response:
        if turn.stream:

            async def stream_response() -> AsyncGenerator[str]:
                token: Token[FoundryAgentRequestContext] | None = set_request_context(context)
                events = self._workflow_events(request, turn, scope, context, partition_key)
                try:
                    async for frame in events:
                        wire_frame = sse_frame(frame["type"], frame)
                        reset_request_context(token)
                        token = None
                        yield wire_frame
                        token = set_request_context(context)
                    reset_request_context(token)
                    token = None
                    yield sse_frame("done", {"session_id": scope.session_id})
                except Exception as exc:
                    logger.exception("Invocations workflow stream failed")
                    message, status, code = _workflow_failure(exc)
                    if token is not None:
                        reset_request_context(token)
                        token = None
                    yield sse_frame("error", {"message": message, "code": code, "status": status})
                finally:
                    if token is None:
                        token = set_request_context(context)
                    try:
                        with CancelScope(shield=True):
                            await events.aclose()
                    finally:
                        reset_request_context(token)

            return _WorkflowStreamingResponse(stream_response(), keep_alive=self.config.sse_keepalive_interval > 0)

        try:
            frames = [frame async for frame in self._workflow_events(request, turn, scope, context, partition_key)]
            return JSONResponse({"output": frames})
        except Exception as exc:
            logger.exception("Invocations workflow request failed")
            message, status, _ = _workflow_failure(exc)
            return JSONResponse({"error": message}, status_code=status)

    async def _workflow_events(
        self,
        request: Request,
        turn: WorkflowTurn[Any],
        scope: FoundryRequestScope,
        context: FoundryAgentRequestContext,
        partition_key: str | tuple[str, str],
    ) -> AsyncGenerator[dict[str, Any]]:
        resolver = self._workflow_resolver
        frames: list[dict[str, Any]] = []
        snapshot_bytes = 0
        deferred: list[dict[str, Any]] = []
        defer = False
        lock = self._session_locks.setdefault(partition_key, asyncio.Lock())
        async with lock:
            workflow = await resolver.resolve(request)
            run = await HostedWorkflowRun.prepare(
                workflow,
                scope=scope,
                response_id=context.call_id or uuid.uuid4().hex,
                config=self.config,
                platform_context=context,
                checkpoint_store_provider=self._checkpoint_storage_provider,
                lineage_id="invocations",
                stored=True,
                replay_completed=True,
                fresh_factory=True,
                reclaim_superseded=True,
            )
            if run.has_completed_output:
                for frame in _workflow_snapshot_frames(run.snapshot):
                    yield frame
                return
            try:
                turn = run.validate_turn(turn)
            except (TypeError, ValueError) as exc:
                raise _WorkflowRequestError(str(exc)) from exc
            if (
                run.stored
                and turn.input is not None
                and isinstance(self._checkpoint_storage_provider, CheckpointStoreProvider)
            ):
                try:
                    self._checkpoint_storage_provider.validate_checkpoint_value(turn.input)
                except WorkflowCheckpointException as exc:
                    raise _WorkflowRequestError(
                        "Stored native workflow input uses an application type that is not checkpoint-allowlisted. "
                        'Configure CheckpointStoreProvider(allowed_checkpoint_types=["module:qualname"]).'
                    ) from exc
            if (
                run.stored
                and turn.responses is not None
                and isinstance(self._checkpoint_storage_provider, CheckpointStoreProvider)
            ):
                try:
                    for reply in turn.responses.values():
                        self._checkpoint_storage_provider.validate_checkpoint_value(reply)
                except WorkflowCheckpointException as exc:
                    raise _WorkflowRequestError(
                        "Stored native workflow reply uses an application type that is not checkpoint-allowlisted. "
                        'Configure CheckpointStoreProvider(allowed_checkpoint_types=["module:qualname"]).'
                    ) from exc
            committed = False
            resources = AsyncExitStack()
            try:
                await run.claim()
                try:
                    entered: set[int] = set()
                    for agent in workflow_agents(workflow):
                        if id(agent) not in entered and isinstance(agent, AbstractAsyncContextManager):
                            entered.add(id(agent))
                            await resources.enter_async_context(agent)
                    events = run.events(turn)
                    resources.push_async_callback(events.aclose)
                    async for event in events:
                        frame = _workflow_frame(event)
                        if frame is None:
                            continue
                        frame_size = _workflow_frame_size(frame)
                        if (
                            len(frames) >= _MAX_WORKFLOW_SNAPSHOT_EVENTS
                            or snapshot_bytes + frame_size > _MAX_WORKFLOW_SNAPSHOT_BYTES
                        ):
                            raise _WorkflowOutputError(
                                "Workflow output exceeds the bounded Invocations snapshot limit."
                            )
                        snapshot_bytes += frame_size
                        frames.append(frame)
                        defer = defer or event.type == "request_info"
                        if defer:
                            deferred.append(frame)
                        else:
                            yield frame
                finally:
                    # Starlette cancellation must not interrupt core/resource cleanup.
                    with CancelScope(shield=True):
                        await resources.__aexit__(*sys.exc_info())
                await run.commit({"output": frames})
                committed = True
            finally:
                if not committed:
                    failure = sys.exc_info()[1]
                    try:
                        with CancelScope(shield=True):
                            await run.abort()
                    except Exception as exc:
                        logger.exception("Failed to persist interrupted Invocations workflow state")
                        if failure is None:
                            raise
                        if isinstance(failure, Exception):
                            raise RuntimeError(
                                "Workflow invocation failed and its interrupted state could not be persisted."
                            ) from exc
        # Pending reply authority is durable, and a reply need not wait on this stream's lock.
        for frame in deferred:
            yield frame
