# Copyright (c) Microsoft. All rights reserved.

"""Host checkpoint-owned native workflows through the Invocations protocol."""

from __future__ import annotations

import asyncio
import inspect
import logging
import sys
import uuid
import weakref
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from contextvars import Token
from typing import Any, Literal

from agent_framework import CheckpointStorage, WorkflowCheckpointException
from agent_framework._telemetry import mark_feature_used
from anyio import CancelScope
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    get_request_context,
    reset_request_context,
    set_request_context,
)
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._feature_usage import FeatureIndex
from ._invocations_shared import (
    _sse,  # pyright: ignore[reportPrivateUsage]
    _workflow_failure,  # pyright: ignore[reportPrivateUsage]
    _workflow_frame,  # pyright: ignore[reportPrivateUsage]
    _workflow_frame_size,  # pyright: ignore[reportPrivateUsage]
    _workflow_snapshot_frames,  # pyright: ignore[reportPrivateUsage]
    _WorkflowOutputError,  # pyright: ignore[reportPrivateUsage]
    _WorkflowRequestError,  # pyright: ignore[reportPrivateUsage]
    _WorkflowStreamingResponse,  # pyright: ignore[reportPrivateUsage]
    invocation_partition_key,
    invocation_request_scope,
)
from ._scope import FoundryRequestScope
from ._shared import (
    CheckpointStoreProvider,
    ContextScopedStoreProvider,
    HostedWorkflowRun,
    WorkflowResolver,
    WorkflowSource,
    WorkflowTurn,
    validate_sse_keep_alive_interval,
    workflow_agents,
)

logger = logging.getLogger(__name__)

_MAX_WORKFLOW_SNAPSHOT_EVENTS = 4096
_MAX_WORKFLOW_SNAPSHOT_BYTES = 4 * 1024 * 1024


class InvocationsWorkflowHostServer(InvocationAgentServerHost):
    """Host a native, checkpoint-owned workflow with application-defined Invocations turns."""

    def __init__(
        self,
        workflow: WorkflowSource[Request],
        *,
        parse_input: Callable[[Request], WorkflowTurn[Any] | Awaitable[WorkflowTurn[Any]]],
        openapi_spec: dict[str, Any] | None = None,
        checkpoint_store_provider: ContextScopedStoreProvider[CheckpointStorage] | None = None,
        sse_keep_alive_interval_seconds: int | None = None,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
        agent_server_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        """Create a native workflow host with explicit parsing and checkpoint ownership.

        Args:
            workflow: Sync or async request-aware factory, called for each request. Build fresh workflows,
                executors, agents, clients, providers, and mutable tools inside the factory. Keep workflow
                and executor IDs stable for checkpoint restoration. The host enters and closes context-managed
                agents; applications own other resource cleanup. Known shared execution resources are rejected.
                Construct tool objects inside the factory. A module-level `@tool` creates a shared wrapper,
                which the ownership guard rejects even for a pure function. A function defined elsewhere can
                be wrapped with `tool(function)` inside the factory; applications still own any captured state.

        Keyword Args:
            parse_input: Sync or async parser returning typed `WorkflowTurn` input or a complete pending
                reply batch. The application validates the request and explicitly supplies workflow kwargs.
            openapi_spec: Application OpenAPI specification forwarded to AgentServer.
            checkpoint_store_provider: Scoped checkpoint storage. Defaults to `CheckpointStoreProvider`.
                Native workflow history and pending replies are checkpoint-owned, not agent-session-owned.
            sse_keep_alive_interval_seconds: Positive streaming heartbeat interval in seconds.
                `None` inherits a positive `SSE_KEEPALIVE_INTERVAL`, otherwise heartbeats are disabled.
                Zero and negative explicit values are invalid. This is not a request or inference timeout.
            log_level: Logging level forwarded unchanged to AgentServer. `None` preserves the SDK default.
            agent_server_kwargs: Caller-owned settings expanded into the AgentServer SDK constructor.
                Hosting does not validate their contents or mutate the mapping. SDK errors propagate.

        Raises:
            TypeError: If the workflow is not a request-aware factory, the parser is invalid,
                or the heartbeat type is invalid.
            ValueError: If the heartbeat interval is nonpositive.
        """
        self._workflow_resolver = WorkflowResolver(workflow)
        if not callable(parse_input):
            raise TypeError("parse_input must be a callable.")
        validate_sse_keep_alive_interval(sse_keep_alive_interval_seconds)
        super().__init__(
            openapi_spec=openapi_spec,
            log_level=log_level,
            **({} if agent_server_kwargs is None else agent_server_kwargs),
        )
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
        """Invoke the native workflow with a trusted request."""
        context = get_request_context()
        try:
            hosted_scope = invocation_request_scope(self.config, request, context)
            partition_key = invocation_partition_key(self.config, context=context, scope=hosted_scope)
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

        scope = hosted_scope or FoundryRequestScope.from_context(self.config, context)
        if turn.stream:

            async def stream_response() -> AsyncGenerator[str]:
                token: Token[FoundryAgentRequestContext] | None = set_request_context(context)
                events = self._workflow_events(request, turn, scope, context, partition_key)
                try:
                    async for frame in events:
                        wire_frame = _sse(frame["type"], frame)
                        reset_request_context(token)
                        token = None
                        yield wire_frame
                        token = set_request_context(context)
                    reset_request_context(token)
                    token = None
                    yield _sse("done", {"session_id": scope.session_id})
                except Exception as exc:
                    logger.exception("Invocations workflow stream failed")
                    message, status, code = _workflow_failure(exc)
                    if token is not None:
                        reset_request_context(token)
                        token = None
                    yield _sse("error", {"message": message, "code": code, "status": status})
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
        frames: list[dict[str, Any]] = []
        snapshot_bytes = 0
        deferred: list[dict[str, Any]] = []
        defer = False
        lock = self._session_locks.setdefault(partition_key, asyncio.Lock())
        async with lock:
            workflow = await self._workflow_resolver.resolve(request)
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
