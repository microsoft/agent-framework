# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from types import TracebackType

from agent_framework import AgentSession, ResponseStream, SessionStore, SupportsAgentRun
from agent_framework._telemetry import mark_feature_used
from anyio import CancelScope
from azure.ai.agentserver.core import FoundryAgentRequestContext, get_request_context
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import Receive, Scope, Send
from typing_extensions import Any, AsyncGenerator

from ._agent_source import is_agent, resolve_agent, validate_agent_source
from ._feature_usage import FeatureIndex
from ._state_store import AgentSessionStoreProvider, StoreProvider

logger = logging.getLogger(__name__)


@dataclass
class _SessionLock:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class _ShieldedAsyncExitStack(AsyncExitStack):
    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> bool | None:
        with CancelScope(shield=True):
            return await super().__aexit__(exc_type, exc, traceback)


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
            # Sending a chunk can fail while the generator is suspended at yield.
            with CancelScope(shield=True):
                try:
                    close = getattr(self.body_iterator, "aclose", None)
                    if close is not None:
                        await close()
                finally:
                    if self.body_iterator is not self._content:
                        await self._content.aclose()


class InvocationsHostServer(InvocationAgentServerHost):
    """An invocations server host for an agent."""

    def __init__(
        self,
        agent: SupportsAgentRun | Callable[[], SupportsAgentRun | Awaitable[SupportsAgentRun]],
        *,
        openapi_spec: dict[str, Any] | None = None,
        agent_session_store_provider: StoreProvider[SessionStore] | None = None,
        session_store_namespace: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an InvocationsHostServer.

        Args:
            agent: The agent to handle responses for, or a zero-argument sync or async callable that creates one for
                each request. Use a callable for agents that keep mutable state outside `AgentSession`.
            openapi_spec: The OpenAPI specification for the server.
            agent_session_store_provider: Provider for conversation session storage. Defaults to Foundry storage
                when hosted and the SDK's file-backed storage locally. New default stores expire sessions 30 days
                after their last write. Custom providers control their own retention.
            session_store_namespace: Stable application identity for session storage. Defaults to the configured
                Foundry agent ID or name. Required for the default store when neither is configured, including
                unnamed local applications. Keep it stable across restarts and distinct for independent applications.
                Custom providers without a namespace are responsible for application and protocol isolation.
            **kwargs: Additional keyword arguments.

        This host will expect the request to be a JSON body with a "message" field.
        The response contains the agent's text, or streamed text when "stream" is true.
        """
        validate_agent_source(agent)
        if session_store_namespace is not None and (
            not isinstance(session_store_namespace, str) or not session_store_namespace.strip()
        ):
            raise ValueError("session_store_namespace must be a non-empty string")
        super().__init__(openapi_spec=openapi_spec, **kwargs)

        self._agent = agent
        self._owns_request_agent = not is_agent(agent)
        self._session_namespace = (
            session_store_namespace
            if session_store_namespace is not None
            else self.config.agent_guid or self.config.agent_name or None
        )
        if agent_session_store_provider is None and (
            self._session_namespace is None or not self._session_namespace.strip()
        ):
            raise ValueError(
                "The default invocation session store requires a stable application identity. "
                "Set session_store_namespace or configure FOUNDRY_AGENT_ID or FOUNDRY_AGENT_NAME."
            )
        self._session_store_provider = (
            AgentSessionStoreProvider(store_name="invocation_sessions")
            if agent_session_store_provider is None
            else agent_session_store_provider
        )
        self._session_locks: dict[str | tuple[str, str], _SessionLock] = {}
        self.invoke_handler(self._handle_invoke)
        mark_feature_used(FeatureIndex.FOUNDRY_HOSTING)

    def _partition_key(self) -> str | tuple[str, str]:
        """Get the partition key for the current request.

        A hosted partition key is a tuple containing the session ID and user ID,
        preserving their boundaries. Locally, the key is just the session ID. In the
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
            return context.session_id, context.user_id

        if not context.session_id:
            raise RuntimeError(
                "The request context is missing session_id. Please ensure that the request is a valid request."
            )

        return context.session_id

    @asynccontextmanager
    async def _request_agent(self) -> AsyncGenerator[SupportsAgentRun]:
        agent = await resolve_agent(self._agent)
        async with _ShieldedAsyncExitStack() as resources:
            if self._owns_request_agent and isinstance(agent, AbstractAsyncContextManager):
                await resources.enter_async_context(agent)
            yield agent

    @asynccontextmanager
    async def _request_session(
        self, partition_key: str | tuple[str, str], context: FoundryAgentRequestContext
    ) -> AsyncGenerator[AgentSession]:
        entry = self._session_locks.get(partition_key)
        if entry is None:
            entry = self._session_locks[partition_key] = _SessionLock()
        entry.users += 1
        try:
            async with entry.lock:
                session_id = (
                    json.dumps(partition_key, separators=(",", ":"))
                    if isinstance(partition_key, tuple)
                    else partition_key
                )
                encoded_key = json.dumps((self._session_namespace, partition_key), separators=(",", ":"))
                storage_key = "invocations:v1:" + hashlib.sha256(encoded_key.encode("utf-8")).hexdigest()
                try:
                    store = self._session_store_provider.get_store(config=self.config, platform_context=context)
                    session = await store.get(storage_key)
                    if session is None:
                        session = AgentSession(session_id=session_id)
                except Exception:
                    logger.exception("Failed to load invocation session")
                    raise

                async def save_session(
                    exc_type: type[BaseException] | None, failure: BaseException | None, traceback: TracebackType | None
                ) -> None:
                    try:
                        await store.set(storage_key, session)
                    except Exception as exc:
                        logger.exception("Failed to persist invocation session")
                        if failure is None:
                            raise
                        if isinstance(failure, Exception):
                            raise RuntimeError(
                                f"Invocation failed: {str(failure) or type(failure).__name__}; "
                                f"session persistence also failed: {str(exc) or type(exc).__name__}"
                            ) from exc
                    except asyncio.CancelledError:
                        logger.error("Invocation session persistence was cancelled")
                        raise

                async with _ShieldedAsyncExitStack() as cleanup:
                    cleanup.push_async_exit(save_session)
                    yield session
        finally:
            entry.users -= 1
            if entry.users == 0:
                del self._session_locks[partition_key]

    async def _handle_invoke(self, request: Request) -> Response:
        """Invoke the agent with the given request."""
        try:
            partition_key = self._partition_key()
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

        context = get_request_context()

        if stream:

            async def stream_response() -> AsyncGenerator[str]:
                async with (
                    self._request_session(partition_key, context) as session,
                    self._request_agent() as agent,
                ):
                    stream = agent.run(user_message, session=session, stream=True)
                    try:
                        async for update in stream:
                            if update.text:
                                yield update.text
                    finally:
                        with CancelScope(shield=True):
                            if isinstance(stream, ResponseStream):
                                await stream.close()
                            else:
                                close = getattr(stream, "aclose", None)
                                if close is not None:
                                    await close()

            return _InvocationStreamingResponse(stream_response())

        async with (
            self._request_session(partition_key, context) as session,
            self._request_agent() as agent,
        ):
            response = await agent.run([user_message], session=session)
        return Response(content=response.text)
