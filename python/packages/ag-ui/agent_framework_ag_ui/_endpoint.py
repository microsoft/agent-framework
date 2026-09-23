# Copyright (c) Microsoft. All rights reserved.

"""FastAPI endpoint creation for AG-UI agents."""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import AsyncGenerator, Sequence
from contextlib import suppress
from inspect import isawaitable
from typing import Any, cast

from ag_ui.core import RunErrorEvent
from ag_ui.encoder import EventEncoder
from agent_framework import CheckpointStorage, SupportsAgentRun, Workflow
from fastapi import FastAPI, HTTPException
from fastapi.params import Depends
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ._agent import AgentFrameworkAgent
from ._approval_state import _APPROVAL_SCOPE_INPUT_KEY
from ._run_common import _extract_resume_payload
from ._snapshots import (
    _DEFAULT_STATE_INPUT_KEY,
    _SNAPSHOT_SCOPE_INPUT_KEY,
    AGUIThreadSnapshotStore,
    SnapshotScopeResolver,
)
from ._types import AGUIRequest
from ._workflow import AgentFrameworkWorkflow

logger = logging.getLogger(__name__)

_DETACHED_READER_START_TIMEOUT_SECONDS = 1.0
_DETACHED_STREAM_QUEUE_SIZE = 16
_KEEPALIVE_COMMENT = "keepalive"


def _get_snapshot_store(
    protocol_runner: AgentFrameworkAgent | AgentFrameworkWorkflow,
) -> AGUIThreadSnapshotStore | None:
    if isinstance(protocol_runner, AgentFrameworkAgent):
        return protocol_runner.config.snapshot_store
    return protocol_runner.snapshot_store


def _set_snapshot_store(
    protocol_runner: AgentFrameworkAgent | AgentFrameworkWorkflow,
    snapshot_store: AGUIThreadSnapshotStore,
) -> None:
    if isinstance(protocol_runner, AgentFrameworkAgent):
        protocol_runner.config.snapshot_store = snapshot_store
        return
    protocol_runner.snapshot_store = snapshot_store


def _configure_snapshot_persistence(
    protocol_runner: AgentFrameworkAgent | AgentFrameworkWorkflow,
    *,
    snapshot_store: AGUIThreadSnapshotStore | None,
    snapshot_scope_resolver: SnapshotScopeResolver | None,
) -> None:
    existing_snapshot_store = _get_snapshot_store(protocol_runner)
    if snapshot_store is not None:
        if existing_snapshot_store is not None and existing_snapshot_store is not snapshot_store:
            raise ValueError("snapshot_store is already configured on the AG-UI runner.")
        if existing_snapshot_store is None:
            _set_snapshot_store(protocol_runner, snapshot_store)
        existing_snapshot_store = snapshot_store

    if existing_snapshot_store is not None and snapshot_scope_resolver is None:
        raise ValueError(
            "snapshot_scope_resolver is required when snapshot_store is configured. "
            "AG-UI Thread ids identify threads but do not authorize snapshot access; "
            "provide a resolver that returns an explicit Snapshot Scope."
        )


def _validate_keepalive_seconds(keepalive_seconds: float | None) -> None:
    if keepalive_seconds is not None and not keepalive_seconds > 0:
        raise ValueError("keepalive_seconds must be positive or None.")


def _validate_detached_run_options(max_detached_runs: int, detached_run_timeout_seconds: float) -> None:
    if max_detached_runs < 1:
        raise ValueError("max_detached_runs must be greater than 0.")
    if detached_run_timeout_seconds <= 0:
        raise ValueError("detached_run_timeout_seconds must be positive.")


def _is_snapshot_hydration_request(
    request: AGUIRequest,
    input_data: dict[str, Any],
    *,
    snapshot_persistence_active: bool,
) -> bool:
    """Return whether a request only replays the latest stored snapshot."""
    if not snapshot_persistence_active or request.messages or _extract_resume_payload(input_data) is not None:
        return False
    forwarded_props = request.forwarded_props or {}
    return not (forwarded_props.get("checkpoint_id") or forwarded_props.get("checkpointId"))


def add_agent_framework_fastapi_endpoint(
    app: FastAPI,
    agent: SupportsAgentRun | AgentFrameworkAgent | Workflow | AgentFrameworkWorkflow,
    path: str = "/",
    state_schema: Any | None = None,
    predict_state_config: dict[str, dict[str, str]] | None = None,
    allow_origins: list[str] | None = None,
    default_state: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    dependencies: Sequence[Depends] | None = None,
    snapshot_store: AGUIThreadSnapshotStore | None = None,
    snapshot_scope_resolver: SnapshotScopeResolver | None = None,
    checkpoint_storage: CheckpointStorage | None = None,
    keepalive_seconds: float | None = 15,
    a2ui_config: dict[str, Any] | None = None,
    detached_runs: bool = False,
    max_detached_runs: int = 32,
    detached_run_timeout_seconds: float = 3600,
) -> None:
    """Add an AG-UI endpoint to a FastAPI app.

    Args:
        app: The FastAPI application
        agent: The agent to expose (can be raw SupportsAgentRun or wrapped)
        path: The endpoint path
        state_schema: Optional state schema for shared state management; accepts dict or Pydantic model/class
        predict_state_config: Optional predictive state update configuration.
            Format: {"state_key": {"tool": "tool_name", "tool_argument": "arg_name"}}
        allow_origins: CORS origins (not yet implemented)
        default_state: Optional initial state to seed when the client does not provide state keys
        tags: OpenAPI tags for endpoint categorization (defaults to ["AG-UI"])
        dependencies: Optional FastAPI dependencies for authentication/authorization.
            These dependencies run before the endpoint handler. Use this to add
            authentication checks, rate limiting, or other middleware-like behavior.
            Example: `dependencies=[Depends(verify_api_key)]`
        snapshot_store: Optional AG-UI Thread Snapshot store. Snapshot persistence is opt-in and requires an
            explicit Snapshot Scope resolver.
        snapshot_scope_resolver: Optional resolver for the application-defined Snapshot Scope. Required whenever
            a snapshot store is configured because an AG-UI Thread id is not an authorization boundary. Also scopes
            the internal Agent Session id used by context providers and in-memory workflow_factory instances when
            provided without a snapshot store. A configured resolver must return a non-empty string derived from
            authorized request context; invalid results fail the request before accessing state or invoking the runner.
        checkpoint_storage: Optional workflow checkpoint storage, applied when the endpoint exposes a workflow.
            When provided, each run creates a checkpoint at the end of every superstep, and a run may resume from
            a persisted checkpoint by supplying its id in the AG-UI forwarded props
            (``forwarded_props: {"checkpoint_id": ...}``).
        keepalive_seconds: Endpoint SSE keepalive interval in seconds. Defaults to 15. Positive values emit fixed
            SSE comments while the stream is open. None disables keepalive and preserves the non-keepalive response
            path. Keepalive comments are transport traffic and do not change AG-UI events.
        a2ui_config: Optional backend A2UI config used when the runtime auto-injects
            the surface-generation tool (``forwardedProps.injectA2UITool``). Keys:
            ``inject_a2ui_tool`` (backend opt-in override), ``default_catalog_id``,
            ``catalog``, ``guidelines``, ``recovery``, ``default_surface_id``.
        detached_runs: Whether agent/workflow execution continues after the SSE client disconnects. Defaults to False.
            When enabled, the endpoint owns a bounded background producer and completes runner persistence even if the
            HTTP reader is cancelled. Request-scoped disposable resources may be released after disconnect, so detached
            work must use values resolved before streaming rather than retaining request-owned clients or sessions.
            This option does not provide resumable event replay.
        max_detached_runs: Maximum number of detached producers retained by this endpoint registration. Defaults to 32.
            Additional requests receive HTTP 503 until capacity is released.
        detached_run_timeout_seconds: Maximum time a producer may remain active after its SSE reader disconnects or
            never starts. Defaults to 3600 seconds. Expired producers are cancelled and release endpoint capacity.
    """
    _validate_keepalive_seconds(keepalive_seconds)
    _validate_detached_run_options(max_detached_runs, detached_run_timeout_seconds)

    protocol_runner: AgentFrameworkAgent | AgentFrameworkWorkflow
    if isinstance(agent, AgentFrameworkWorkflow):
        protocol_runner = agent
    elif isinstance(agent, AgentFrameworkAgent):
        protocol_runner = agent
    elif isinstance(agent, Workflow):
        protocol_runner = AgentFrameworkWorkflow(workflow=agent)
    elif isinstance(agent, SupportsAgentRun):
        protocol_runner = AgentFrameworkAgent(
            agent=agent,
            state_schema=state_schema,
            predict_state_config=predict_state_config,
            snapshot_store=snapshot_store,
            a2ui_config=a2ui_config,
        )
    else:
        raise TypeError("agent must be SupportsAgentRun, Workflow, AgentFrameworkAgent, or AgentFrameworkWorkflow.")

    if checkpoint_storage is not None:
        if not isinstance(protocol_runner, AgentFrameworkWorkflow):
            raise ValueError("checkpoint_storage is only supported when the endpoint exposes a workflow.")
        # A pre-wrapped runner without storage adopts the endpoint's; a runner that
        # already carries a different storage is a configuration conflict.
        if (
            protocol_runner.checkpoint_storage is not None
            and protocol_runner.checkpoint_storage is not checkpoint_storage
        ):
            raise ValueError("checkpoint_storage is already configured on the AG-UI workflow runner.")
        protocol_runner.checkpoint_storage = checkpoint_storage

    _configure_snapshot_persistence(
        protocol_runner,
        snapshot_store=snapshot_store,
        snapshot_scope_resolver=snapshot_scope_resolver,
    )

    background_tasks: set[asyncio.Task[Any]] = set()
    producer_tasks: set[asyncio.Task[None]] = set()
    active_runs: dict[tuple[str | None, str], asyncio.Task[None]] = {}

    def retain_background_task(task: asyncio.Task[Any]) -> None:
        background_tasks.add(task)

        def task_done(completed: asyncio.Task[Any]) -> None:
            background_tasks.discard(completed)
            if completed.cancelled():
                return
            exception = completed.exception()
            if exception is not None:
                logger.error(
                    "[%s] Detached stream task failed",
                    path,
                    exc_info=(type(exception), exception, exception.__traceback__),
                )

        task.add_done_callback(task_done)

    @app.post(path, tags=tags or ["AG-UI"], dependencies=dependencies, response_model=None)  # type: ignore[arg-type]
    async def agent_endpoint(request_body: AGUIRequest) -> Response:
        """Handle AG-UI agent requests.

        Note: Function is accessed via FastAPI's decorator registration,
        despite appearing unused to static analysis.
        """
        try:
            input_data = request_body.model_dump(exclude_none=True)
            snapshot_persistence_active = _get_snapshot_store(protocol_runner) is not None
            snapshot_scope: str | None = None
            if snapshot_scope_resolver is not None:
                resolved_scope = snapshot_scope_resolver(request_body)
                if isawaitable(resolved_scope):
                    resolved_scope = await resolved_scope
                if not isinstance(resolved_scope, str) or not resolved_scope:
                    raise ValueError("snapshot_scope_resolver must return a non-empty string.")
                snapshot_scope = resolved_scope
                input_data[_APPROVAL_SCOPE_INPUT_KEY] = snapshot_scope
                input_data[_SNAPSHOT_SCOPE_INPUT_KEY] = snapshot_scope
            if default_state:
                if snapshot_persistence_active:
                    # Defer default application to the runner so defaults only fill keys
                    # missing from both the stored snapshot state and the request state.
                    input_data[_DEFAULT_STATE_INPUT_KEY] = copy.deepcopy(default_state)
                else:
                    state = input_data.setdefault("state", {})
                    for key, value in default_state.items():
                        if key not in state:
                            state[key] = copy.deepcopy(value)
            logger.debug(
                f"[{path}] Received request - Run ID: {input_data.get('run_id', 'no-run-id')}, "
                f"Thread ID: {input_data.get('thread_id', 'no-thread-id')}, "
                f"Messages: {len(input_data.get('messages', []))}"
            )
            logger.info(f"Received request at {path}: {input_data.get('run_id', 'no-run-id')}")

            keepalive_enabled = keepalive_seconds is not None
            active_run_key: tuple[str | None, str] | None = None
            if (
                detached_runs
                and request_body.thread_id is not None
                and not _is_snapshot_hydration_request(
                    request_body,
                    input_data,
                    snapshot_persistence_active=snapshot_persistence_active,
                )
            ):
                active_run_key = (snapshot_scope, request_body.thread_id)
                active_task = active_runs.get(active_run_key)
                if active_task is not None and not active_task.done():
                    return JSONResponse(
                        status_code=409,
                        content={"detail": "An AG-UI run is already active for this scoped thread."},
                    )
                active_runs.pop(active_run_key, None)
            if detached_runs:
                for completed_task in tuple(producer_tasks):
                    if completed_task.done():
                        producer_tasks.discard(completed_task)
                if len(producer_tasks) >= max_detached_runs:
                    return JSONResponse(
                        status_code=503,
                        content={"detail": "AG-UI detached run capacity is exhausted."},
                    )

            def prepare_frame(encoded: str) -> str | bytes:
                if keepalive_enabled:
                    return encoded.encode("utf-8")
                return encoded

            async def event_generator() -> AsyncGenerator[str | bytes]:
                encoder = EventEncoder()
                event_count = 0
                try:
                    async for event in protocol_runner.run(input_data):
                        event_count += 1
                        event_type_name = getattr(event, "type", type(event).__name__)
                        # Log important events at INFO level
                        if "TOOL_CALL" in str(event_type_name) or "RUN" in str(event_type_name):
                            if hasattr(event, "model_dump"):
                                event_data = event.model_dump(exclude_none=True)
                                logger.info(f"[{path}] Event {event_count}: {event_type_name} - {event_data}")
                            else:
                                logger.info(f"[{path}] Event {event_count}: {event_type_name}")

                        try:
                            encoded = encoder.encode(event)
                        except Exception as encode_error:
                            logger.exception("[%s] Failed to encode event %s", path, event_type_name)
                            run_error = RunErrorEvent(
                                message="An internal error has occurred while streaming events.",
                                code=type(encode_error).__name__,
                            )
                            try:
                                yield prepare_frame(encoder.encode(run_error))
                            except Exception:
                                logger.exception("[%s] Failed to encode RUN_ERROR event", path)
                            return

                        logger.debug(
                            f"[{path}] Encoded as: {encoded[:200]}..."
                            if len(encoded) > 200
                            else f"[{path}] Encoded as: {encoded}"
                        )
                        yield prepare_frame(encoded)

                    logger.info(f"[{path}] Completed streaming {event_count} events")
                except Exception as stream_error:
                    logger.exception("[%s] Streaming failed", path)
                    run_error = RunErrorEvent(
                        message="An internal error has occurred while streaming events.",
                        code=type(stream_error).__name__,
                    )
                    try:
                        yield prepare_frame(encoder.encode(run_error))
                    except Exception:
                        logger.exception("[%s] Failed to encode RUN_ERROR event", path)

            async def drain_detached_stream(queue: asyncio.Queue[str | bytes | None]) -> None:
                while await queue.get() is not None:
                    pass

            stream: AsyncGenerator[str | bytes]
            if detached_runs:
                queue: asyncio.Queue[str | bytes | None] = asyncio.Queue(maxsize=_DETACHED_STREAM_QUEUE_SIZE)
                reader_started = asyncio.Event()
                reader_abandoned = asyncio.Event()

                async def produce_events() -> None:
                    try:
                        async for frame in event_generator():
                            if reader_abandoned.is_set():
                                continue
                            if not reader_started.is_set():
                                try:
                                    queue.put_nowait(frame)
                                except asyncio.QueueFull:
                                    reader_abandoned.set()
                                    while True:
                                        try:
                                            queue.get_nowait()
                                        except asyncio.QueueEmpty:
                                            break
                                continue
                            await queue.put(frame)
                    except asyncio.CancelledError:
                        reader_abandoned.set()
                        raise
                    finally:
                        current_task = asyncio.current_task()
                        if active_run_key is not None and active_runs.get(active_run_key) is current_task:
                            active_runs.pop(active_run_key, None)
                        if reader_started.is_set() or not reader_abandoned.is_set():
                            await queue.put(None)

                producer_task = asyncio.create_task(
                    produce_events(),
                    name=f"ag-ui-run-{input_data.get('run_id', 'generated')}",
                )
                if active_run_key is not None:
                    active_runs[active_run_key] = producer_task
                producer_tasks.add(producer_task)
                producer_task.add_done_callback(producer_tasks.discard)
                retain_background_task(producer_task)

                async def expire_abandoned_run() -> None:
                    if not reader_started.is_set():
                        try:
                            await asyncio.wait_for(
                                reader_started.wait(),
                                timeout=_DETACHED_READER_START_TIMEOUT_SECONDS,
                            )
                        except asyncio.TimeoutError:
                            reader_abandoned.set()
                    if producer_task.done():
                        return
                    if not reader_abandoned.is_set():
                        abandoned_wait = asyncio.create_task(reader_abandoned.wait())
                        done, _ = await asyncio.wait(
                            {producer_task, abandoned_wait},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if producer_task in done:
                            abandoned_wait.cancel()
                            with suppress(asyncio.CancelledError):
                                await abandoned_wait
                            return
                    if producer_task.done():
                        return
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(producer_task),
                            timeout=detached_run_timeout_seconds,
                        )
                    except asyncio.TimeoutError:
                        logger.error(
                            "[%s] Detached run exceeded %.1f seconds after reader disconnect; cancelling",
                            path,
                            detached_run_timeout_seconds,
                        )
                        reader_abandoned.set()
                        producer_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await producer_task

                expiry_task = asyncio.create_task(
                    expire_abandoned_run(),
                    name=f"ag-ui-expiry-{input_data.get('run_id', 'generated')}",
                )
                retain_background_task(expiry_task)

                async def detached_event_generator() -> AsyncGenerator[str | bytes]:
                    completed = False
                    try:
                        reader_started.set()
                        if reader_abandoned.is_set():
                            return
                        while True:
                            item = await queue.get()
                            if item is None:
                                completed = True
                                return
                            yield item
                    finally:
                        if not completed and not producer_task.done():
                            reader_abandoned.set()
                            drain_task = asyncio.create_task(
                                drain_detached_stream(queue),
                                name=f"ag-ui-drain-{input_data.get('run_id', 'generated')}",
                            )
                            retain_background_task(drain_task)

                stream = detached_event_generator()
            else:
                stream = event_generator()

            headers = {
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
            if keepalive_seconds is not None:
                from sse_starlette.event import ServerSentEvent
                from sse_starlette.sse import EventSourceResponse

                return EventSourceResponse(
                    stream,
                    ping=cast(int, keepalive_seconds),
                    ping_message_factory=lambda: ServerSentEvent(comment=_KEEPALIVE_COMMENT),
                    headers=headers,
                    media_type="text/event-stream",
                )
            return StreamingResponse(
                stream,
                media_type="text/event-stream",
                headers=headers,
            )
        except Exception as e:
            logger.error(f"Error in agent endpoint: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="An internal error has occurred.") from e
