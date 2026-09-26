# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager

from agent_framework import AgentSession, ResponseStream, SessionStore, SupportsAgentRun
from agent_framework._telemetry import mark_feature_used
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


class InvocationsHostServer(InvocationAgentServerHost):
    """An invocations server host for an agent."""

    def __init__(
        self,
        agent: SupportsAgentRun | Callable[[], SupportsAgentRun | Awaitable[SupportsAgentRun]],
        *,
        openapi_spec: dict[str, Any] | None = None,
        agent_session_store_provider: StoreProvider[SessionStore] | None = None,
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
            **kwargs: Additional keyword arguments.

        This host will expect the request to be a JSON body with a "message" field.
        The response contains the agent's text, or streamed text when "stream" is true.
        """
        validate_agent_source(agent)
        super().__init__(openapi_spec=openapi_spec, **kwargs)

        self._agent = agent
        self._owns_request_agent = not is_agent(agent)
        self._session_store_provider = (
            AgentSessionStoreProvider(store_name="invocation_sessions")
            if agent_session_store_provider is None
            else agent_session_store_provider
        )
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
        async with AsyncExitStack() as resources:
            if self._owns_request_agent and isinstance(agent, AbstractAsyncContextManager):
                await resources.enter_async_context(agent)
            yield agent

    @asynccontextmanager
    async def _request_session(
        self, partition_key: str | tuple[str, str], context: FoundryAgentRequestContext
    ) -> AsyncGenerator[AgentSession]:
        session_id = (
            json.dumps(partition_key, separators=(",", ":")) if isinstance(partition_key, tuple) else partition_key
        )
        try:
            store = self._session_store_provider.get_store(config=self.config, platform_context=context)
            session = await store.get(session_id)
            if session is None:
                session = AgentSession(session_id=session_id)
        except Exception:
            logger.exception("Failed to load invocation session")
            raise
        try:
            yield session
        finally:
            failure = sys.exc_info()[1]
            try:
                await store.set(session_id, session)
            except Exception as exc:
                logger.exception("Failed to persist invocation session")
                if failure is None:
                    raise
                if isinstance(failure, Exception):
                    raise RuntimeError(
                        f"Invocation failed: {str(failure) or type(failure).__name__}; "
                        f"session persistence also failed: {str(exc) or type(exc).__name__}"
                    ) from exc

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
