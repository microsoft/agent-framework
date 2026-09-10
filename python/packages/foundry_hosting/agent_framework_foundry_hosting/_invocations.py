# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import sys
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager, suppress
from typing import cast

from agent_framework import (
    AgentSession,
    CheckpointStorage,
    FunctionalWorkflowAgent,
    SessionStore,
    WorkflowAgent,
    WorkflowRunState,
)
from agent_framework._filesystem import _storage_key_segment  # pyright: ignore[reportPrivateUsage]
from agent_framework._telemetry import mark_feature_used
from anyio import CancelScope
from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import Send
from typing_extensions import Any, AsyncGenerator

from ._agent_factory import (
    AgentFactory,
    AgentFactoryResolver,
    HostedAgent,
    ScopeLocks,
    close_run_iterator,
    is_workflow_agent,
    validate_agent_source,
)
from ._feature_usage import FeatureIndex
from ._state_store import (
    ContextScopedStoreProvider,
    StoreProvider,
    _CheckpointStorageWithErrors,  # pyright: ignore[reportPrivateUsage]
    _InvocationsAgentSessionStoreProvider,  # pyright: ignore[reportPrivateUsage]
    _InvocationsCheckpointStoreProvider,  # pyright: ignore[reportPrivateUsage]
)

_WORKFLOW_STATE_KEY = "_foundry_invocations_workflow"
_PENDING_REQUEST_ERROR = (
    "Invocations plain text cannot answer workflow pending requests or approvals. "
    "Use a protocol that supports structured workflow responses."
)


class _InvocationStreamingResponse(StreamingResponse):
    async def stream_response(self, send: Send) -> None:
        # Starlette does not close a body iterator suspended at yield when send fails.
        # Close it in the consumer task, where task-affine agent resources were entered.
        try:
            await super().stream_response(send)
        except BaseException as exc:
            with suppress(StopAsyncIteration):
                await cast(AsyncGenerator[str], self.body_iterator).athrow(exc)
            raise
        finally:
            await cast(AsyncGenerator[str], self.body_iterator).aclose()


class InvocationsHostServer(InvocationAgentServerHost):
    """An invocations server host for an agent."""

    def __init__(
        self,
        agent: HostedAgent | None = None,
        *,
        agent_factory: AgentFactory | None = None,
        checkpoint_store_provider: ContextScopedStoreProvider[CheckpointStorage] | None = None,
        agent_session_store_provider: StoreProvider[SessionStore] | None = None,
        openapi_spec: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an InvocationsHostServer.

        Args:
            agent: An ordinary agent instance. Supply workflows through agent_factory instead.
            agent_factory: A sync or async callable creating an agent for each request. Recreate
                workflows, mutable executors, providers, and tools. An async context manager
                returned by the factory is entered and exited within that request.
            checkpoint_store_provider: Optional provider for user/session-scoped workflow checkpoints.
            agent_session_store_provider: Optional provider for persisted workflow provider state.
            openapi_spec: The OpenAPI specification for the server.
            **kwargs: Additional keyword arguments.

        This host will expect the request to be a JSON body with a "message" field.
        Responses contain plain text; "stream": true streams text as text/event-stream.
        Workflow factories must use stable workflow names and executor IDs across requests.
        The text-only exchange cannot answer pending workflow requests or approvals.
        Functional workflows support fresh messages after clean completion, but not
        pending or interrupted continuation. Such continuation fails explicitly.
        Factories own cleanup of nested resources not exposed by an async context manager.
        """
        validate_agent_source(agent, agent_factory)
        super().__init__(openapi_spec=openapi_spec, **kwargs)

        self._agent = agent
        self._agent_resolver = AgentFactoryResolver(agent_factory) if agent_factory is not None else None
        self._scope_locks = ScopeLocks()
        self._checkpoint_storage_provider = (
            _InvocationsCheckpointStoreProvider() if checkpoint_store_provider is None else checkpoint_store_provider
        )
        self._agent_session_storage_provider = (
            _InvocationsAgentSessionStoreProvider()
            if agent_session_store_provider is None
            else agent_session_store_provider
        )
        self._sessions: dict[str, AgentSession] = {}
        self.invoke_handler(self._handle_invoke)
        mark_feature_used(FeatureIndex.FOUNDRY_HOSTING)

    def _partition_key(self) -> str:
        """Get the partition key for the current request.

        A partition key is made up of the session ID and user ID. If the request is not
        from a hosted environment, the partition key will be just the session ID. In the
        Foundry hosted environment, the partition key is used to maintain isolation between
        different sessions and users, such that one user cannot access another user's sessions.

        Returns:
            The partition key for the current request.

        Exceptions:
            RuntimeError: If the context doesn't contain the expected IDs.
        """
        context = get_request_context()

        if self.config.is_hosted:
            if not context.session_id or not context.user_id:
                raise RuntimeError(
                    "The hosted environment is missing session_id or user_id in the request context. "
                    "Please ensure that the request is coming from a valid Foundry platform service."
                )
            return f"{context.session_id}:{context.user_id}"

        if not context.session_id:
            raise RuntimeError(
                "The request context is missing session_id. Please ensure that the request is a valid request."
            )

        return context.session_id

    @asynccontextmanager
    async def _request_agent(self, scope: tuple[str | None, str]) -> AsyncGenerator[tuple[HostedAgent, CancelScope]]:
        async with self._scope_locks.hold(scope):
            # Enter before the agent's own task groups. Adding a new cancel scope
            # around their exit would violate AnyIO's required scope nesting.
            with CancelScope() as cleanup_scope:
                agent = await cast(AgentFactoryResolver, self._agent_resolver).resolve()
                resources = AsyncExitStack()
                try:
                    if isinstance(agent, AbstractAsyncContextManager):
                        await resources.enter_async_context(agent)
                    yield agent, cleanup_scope
                finally:
                    cleanup_scope.shield = True
                    exc_info = sys.exc_info()
                    if isinstance(exc_info[1], GeneratorExit):
                        await resources.aclose()
                    else:
                        await resources.__aexit__(*exc_info)

    @asynccontextmanager
    async def _workflow_session(
        self, agent: WorkflowAgent | FunctionalWorkflowAgent, storage_id: str
    ) -> AsyncGenerator[tuple[AgentSession, CheckpointStorage]]:
        context = get_request_context()
        storage = _CheckpointStorageWithErrors(
            self._checkpoint_storage_provider.get_store(
                config=self.config, context_id=storage_id, platform_context=context
            )
        )
        sessions = self._agent_session_storage_provider.get_store(config=self.config, platform_context=context)
        workflow = agent.workflow if isinstance(agent, WorkflowAgent) else agent._workflow  # pyright: ignore[reportPrivateUsage]
        kind = "graph" if isinstance(agent, WorkflowAgent) else "functional"
        if isinstance(agent, WorkflowAgent):
            storage.observe_workflow(agent)
        session = await sessions.get(storage_id)
        saved_marker = session.state.get(_WORKFLOW_STATE_KEY) if session is not None else None
        marker = cast(dict[str, Any], saved_marker) if isinstance(saved_marker, dict) else None
        if session is not None and (
            marker is None or marker.get("name") != workflow.name or marker.get("kind") != kind
        ):
            raise RuntimeError("The stored Invocations workflow name or kind does not match the factory result.")
        checkpoint = await storage.get_latest(workflow_name=workflow.name)
        if checkpoint is not None and checkpoint.workflow_name != workflow.name:
            raise RuntimeError("The stored Invocations checkpoint does not match the workflow name.")
        if marker is not None and checkpoint is None:
            raise RuntimeError("The existing Invocations workflow session is missing its required checkpoint.")
        if checkpoint is not None and session is None:
            raise RuntimeError("The existing Invocations workflow checkpoint is missing its required agent session.")
        if marker is not None and marker.get("checkpoint_failed"):
            raise RuntimeError("The previous Invocations workflow run has incomplete checkpoint persistence.")
        if isinstance(agent, FunctionalWorkflowAgent) and marker is not None and marker.get("completed") is not True:
            raise RuntimeError("Invocations cannot continue a pending or interrupted functional workflow.")
        if isinstance(agent, WorkflowAgent) and checkpoint is not None:
            if checkpoint.pending_request_info_events:
                raise RuntimeError(_PENDING_REQUEST_ERROR)
            await agent.workflow.run(checkpoint_id=checkpoint.checkpoint_id, checkpoint_storage=storage)
            if storage.save_error is not None:
                raise storage.save_error
            if agent.workflow.status == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
                raise RuntimeError(_PENDING_REQUEST_ERROR)
        if session is None:
            session = AgentSession(session_id=storage_id)
        marker = {"name": workflow.name, "kind": kind, "completed": False}
        session.state[_WORKFLOW_STATE_KEY] = marker
        # Record the attempt before execution. A failed first run must not look like a new session.
        await sessions.set(storage_id, session)
        try:
            yield session, storage
            if storage.save_error is not None:
                raise storage.save_error
            pending = (
                agent.workflow.status == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
                if isinstance(agent, WorkflowAgent)
                else bool(agent.pending_requests)
            )
            if pending:
                raise RuntimeError(_PENDING_REQUEST_ERROR)
            if await storage.get_latest(workflow_name=workflow.name) is None:
                raise RuntimeError("The Invocations workflow did not persist a required checkpoint.")
            marker["completed"] = True
        finally:
            if storage.save_error is not None:
                marker["checkpoint_failed"] = True
            with CancelScope(shield=True):
                await sessions.set(storage_id, session)

    @asynccontextmanager
    async def _factory_session(
        self, agent: HostedAgent, storage_id: str
    ) -> AsyncGenerator[tuple[AgentSession, dict[str, Any]]]:
        if is_workflow_agent(agent):
            async with self._workflow_session(agent, storage_id) as (session, storage):
                yield session, {"checkpoint_storage": storage}
        else:
            yield self._sessions.setdefault(storage_id, AgentSession(session_id=storage_id)), {}

    async def _handle_factory_invoke(self, user_message: Any, *, stream: bool) -> Response:
        context = get_request_context()
        scope = (context.user_id, cast(str, context.session_id))
        storage_id = _storage_key_segment(json.dumps(scope, ensure_ascii=False), encoded_prefix="~invocations-")

        if stream:

            async def stream_response() -> AsyncGenerator[str]:
                async with (
                    self._request_agent(scope) as (agent, cleanup_scope),
                    self._factory_session(agent, storage_id) as (
                        session,
                        run_kwargs,
                    ),
                ):
                    iterator = agent.run(user_message, session=session, stream=True, **run_kwargs).__aiter__()
                    try:
                        async for update in iterator:
                            if update.text:
                                yield update.text
                    finally:
                        cleanup_scope.shield = True
                        await close_run_iterator(iterator)

            return _InvocationStreamingResponse(
                stream_response(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

        async with (
            self._request_agent(scope) as (agent, _),
            self._factory_session(agent, storage_id) as (
                session,
                run_kwargs,
            ),
        ):
            response = await agent.run([user_message], session=session, **run_kwargs)
        return Response(content=response.text)

    async def _handle_invoke(self, request: Request) -> Response:
        """Invoke the agent with the given request."""
        try:
            session_id = self._partition_key()
        except Exception as e:
            return Response(content=str(e), status_code=500)

        data = await request.json()

        stream = data.get("stream", False)
        user_message = data.get("message", None)
        if user_message is None:
            error = "Missing 'message' in request"
            if stream:
                return StreamingResponse(content=error, status_code=400)
            return Response(content=error, status_code=400)

        if self._agent_resolver is not None:
            return await self._handle_factory_invoke(user_message, stream=stream)

        agent = cast(HostedAgent, self._agent)
        session = self._sessions.setdefault(session_id, AgentSession(session_id=session_id))

        if stream:

            async def stream_response() -> AsyncGenerator[str]:
                async for update in agent.run(user_message, session=session, stream=True):
                    if update.text:
                        yield update.text

            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

        response = await agent.run([user_message], session=session)
        return Response(content=response.text)
