# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sys
import warnings
import weakref
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from contextvars import Token
from copy import deepcopy
from typing import cast

from agent_framework import AgentSession, ResponseStream, SessionStore, SupportsAgentRun
from agent_framework._telemetry import mark_feature_used
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    get_request_context,
    reset_request_context,
    set_request_context,
)
from azure.ai.agentserver.core.storage import FoundryStorageConflictError, FoundryStoragePreconditionError
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.types import Receive, Scope, Send
from typing_extensions import Any

from ._agent_source import AgentSource, is_agent, resolve_agent, validate_agent_source
from ._feature_usage import FeatureIndex
from ._request import InvocationRun, UnsupportedOptions, validate_request_options, validate_unsupported_options
from ._scope import FoundryRequestScope
from ._state_store import AgentSessionStoreProvider, StoreProvider

logger = logging.getLogger(__name__)

InvocationParser = Callable[[Request], InvocationRun | Awaitable[InvocationRun]]
InvocationOptionsHook = Callable[[Request, dict[str, Any]], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]

_AGENT_CONTROLLED_FIELDS = frozenset({
    "additional_function_arguments",
    "client_kwargs",
    "compaction_strategy",
    "function_invocation_kwargs",
    "instructions",
    "middleware",
    "session",
    "tokenizer",
    "tools",
})


class _UnsupportedAgentOptions(TypeError):
    """The agent cannot accept the caller's run options under the selected policy."""


def _sse(event: str, data: Mapping[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _invocation_failure(exc: Exception) -> tuple[str, int, str]:
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, (FoundryStorageConflictError, FoundryStoragePreconditionError)):
            return "Another request advanced this agent session; reload before retrying.", 409, "session_conflict"
        cause = cause.__cause__
    return "Agent invocation failed.", 500, "invocation_failed"


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
    """Host an agent with durable sessions and application-defined Invocations input."""

    def __init__(
        self,
        agent: AgentSource,
        *,
        openapi_spec: dict[str, Any] | None = None,
        agent_session_store_provider: StoreProvider[SessionStore] | None = None,
        parse_request: InvocationParser | None = None,
        prepare_options: InvocationOptionsHook | None = None,
        unsupported_options: UnsupportedOptions = "warn",
        legacy_wire_format: bool = False,
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
            parse_request: Optional sync or async parser returning an `InvocationRun` from application JSON.
                Without one, accepts a JSON object with `message`, optional `options`, and optional `stream`.
            prepare_options: Optional sync or async hook to filter or replace a copy of caller generation options.
                Tool context and agent execution controls must remain in developer-owned agent configuration.
            unsupported_options: `"warn"` (default), `"ignore"`, or `"error"` for agents without runtime options.
            legacy_wire_format: Opt into the deprecated plain-text response and raw streaming chunks instead of
                the default JSON response and framed `delta`/`done`/`error` server-sent events.
            **kwargs: Additional keyword arguments.
        """
        validate_agent_source(agent)
        if parse_request is not None and not callable(parse_request):
            raise TypeError("parse_request must be a callable.")
        if prepare_options is not None and not callable(prepare_options):
            raise TypeError("prepare_options must be a callable.")
        if not isinstance(legacy_wire_format, bool):
            raise TypeError("legacy_wire_format must be a boolean.")
        super().__init__(openapi_spec=openapi_spec, **kwargs)

        self._agent = agent
        self._owns_request_agent = not is_agent(agent)
        self._parse_request = parse_request
        self._prepare_options = prepare_options
        self._unsupported_options = validate_unsupported_options(unsupported_options)
        self._legacy_wire_format = legacy_wire_format
        self._session_store_provider = (
            AgentSessionStoreProvider(store_name="invocation_sessions")
            if agent_session_store_provider is None
            else agent_session_store_provider
        )
        self._session_locks: weakref.WeakValueDictionary[str | tuple[str, str], asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        if legacy_wire_format:
            message = (
                "legacy_wire_format=True is deprecated; migrate Invocations clients to JSON responses "
                "and framed SSE events before removing this compatibility mode."
            )
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            logger.warning("DEPRECATION: %s", message)
        self.invoke_handler(self._handle_invoke)
        mark_feature_used(FeatureIndex.FOUNDRY_HOSTING)

    def _partition_key(
        self,
        *,
        context: FoundryAgentRequestContext | None = None,
        scope: FoundryRequestScope | None = None,
    ) -> str | tuple[str, str]:
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
        if context is None:
            context = get_request_context()

        if self.config.is_hosted:
            if not context.user_id:
                raise RuntimeError(
                    "The hosted environment is missing user_id in the request context. "
                    "Please ensure that the request is coming from a valid Foundry platform service."
                )
            hosted_scope = scope or FoundryRequestScope.from_context(self.config, context)
            return hosted_scope.session_id, context.user_id

        if not context.session_id:
            raise RuntimeError(
                "The request context is missing session_id. Please ensure that the request is a valid request."
            )

        return context.session_id

    def _hosted_scope(self, request: Request, context: FoundryAgentRequestContext) -> FoundryRequestScope:
        """Accept an unconfigured session only when the routed Invocations query identifies it."""
        if not context.user_id:
            raise RuntimeError("The hosted environment is missing user_id in the request context.")

        routed_session_ids = request.query_params.getlist("agent_session_id")
        if len(routed_session_ids) > 1:
            raise RuntimeError("Hosted Invocations requires exactly one agent_session_id query parameter.")
        routed_session_id = routed_session_ids[0] if routed_session_ids else None
        if self.config.session_id:
            if routed_session_id is not None and routed_session_id != self.config.session_id:
                raise RuntimeError("The request agent_session_id does not match the platform session ID.")
            return FoundryRequestScope.from_context(self.config, context)

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

    @asynccontextmanager
    async def _request_agent(self) -> AsyncGenerator[SupportsAgentRun]:
        agent = await resolve_agent(self._agent)
        async with AsyncExitStack() as resources:
            if self._owns_request_agent and isinstance(agent, AbstractAsyncContextManager):
                await resources.enter_async_context(agent)
            yield agent

    @asynccontextmanager
    async def _request_session(
        self,
        partition_key: str | tuple[str, str],
        context: FoundryAgentRequestContext,
        *,
        hosted_scope: FoundryRequestScope | None = None,
    ) -> AsyncGenerator[AgentSession]:
        session_id = (
            json.dumps(partition_key, separators=(",", ":")) if isinstance(partition_key, tuple) else partition_key
        )
        try:
            provider = self._session_store_provider
            if hosted_scope is not None and not self.config.session_id and type(provider) is AgentSessionStoreProvider:
                store = provider._get_scoped_store(context, hosted_scope)  # pyright: ignore[reportPrivateUsage]
            else:
                store = provider.get_store(config=self.config, platform_context=context)
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

    async def _parse(self, request: Request) -> InvocationRun:
        if self._parse_request is not None:
            result = self._parse_request(request)
            parsed = await result if inspect.isawaitable(result) else result
            if not isinstance(parsed, InvocationRun):
                raise TypeError("parse_request must return InvocationRun.")
            return parsed

        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("The invocation must be a JSON object.")
        body = cast(Mapping[str, Any], payload)
        message = body.get("message")
        stream = body.get("stream", False)
        options = body.get("options", {})
        if not isinstance(message, str):
            raise ValueError("message must be a string.")
        if not isinstance(stream, bool):
            raise ValueError("stream must be a boolean.")
        if not isinstance(options, dict):
            raise ValueError("options must be an object.")
        return InvocationRun(
            messages=message if stream else [message], options=cast(Mapping[str, Any], options), stream=stream
        )

    async def _options(self, request: Request, parsed: InvocationRun) -> dict[str, Any]:
        options = deepcopy(dict(parsed.options))
        if self._prepare_options is not None:
            result = self._prepare_options(request, options)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, Mapping) or any(not isinstance(key, str) for key in result):
                raise TypeError("prepare_options must return a mapping of MAF run options with string keys.")
            options = deepcopy(dict(result))
        validate_request_options(options)
        reserved = _AGENT_CONTROLLED_FIELDS.intersection(options)
        if reserved:
            raise ValueError(f"Invocations options cannot set agent-controlled fields: {', '.join(sorted(reserved))}.")
        return options

    def _agent_kwargs(self, agent: SupportsAgentRun, options: dict[str, Any]) -> dict[str, Any]:
        if not options:
            return {}
        try:
            inspect.signature(agent.run).bind_partial(options=options)
        except (TypeError, ValueError):
            if self._unsupported_options == "error":
                raise _UnsupportedAgentOptions("The hosted agent does not accept caller runtime options.") from None
            if self._unsupported_options == "warn":
                logger.warning("Agent doesn't support runtime options. They will be ignored.")
            return {}
        return {"options": options}

    @staticmethod
    async def _close_interrupted_stream(stream: object) -> None:
        if isinstance(stream, ResponseStream):
            close = getattr(cast(object, stream), "close", None)
            if close is None:
                logger.warning("The installed core cannot close an interrupted agent stream.")
                return
        else:
            close = getattr(stream, "aclose", None)
        if close is not None:
            await close()

    async def _handle_invoke(self, request: Request) -> Response:
        """Invoke the agent with the given request."""
        context = get_request_context()
        try:
            hosted_scope = self._hosted_scope(request, context) if self.config.is_hosted else None
            partition_key = self._partition_key(context=context, scope=hosted_scope)
        except RuntimeError as exc:
            logger.error("Failed to resolve Invocations session: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

        try:
            parsed = await self._parse(request)
            options = await self._options(request, parsed)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception:
            logger.exception("Failed to prepare Invocations request")
            return JSONResponse({"error": "Failed to prepare invocation request."}, status_code=500)

        if parsed.stream:
            if options and self._unsupported_options == "error" and is_agent(self._agent):
                try:
                    self._agent_kwargs(self._agent, options)
                except _UnsupportedAgentOptions as exc:
                    return JSONResponse({"error": str(exc)}, status_code=400)

            async def stream_response() -> AsyncGenerator[str]:
                token: Token[FoundryAgentRequestContext] | None = set_request_context(context)
                try:
                    lock = self._session_locks.setdefault(partition_key, asyncio.Lock())
                    async with lock, self._request_agent() as agent:
                        run_kwargs = self._agent_kwargs(agent, options)
                        async with self._request_session(partition_key, context, hosted_scope=hosted_scope) as session:
                            stream = agent.run(parsed.messages, session=session, stream=True, **run_kwargs)
                            completed = False
                            try:
                                async for update in stream:
                                    if update.text:
                                        frame = (
                                            update.text
                                            if self._legacy_wire_format
                                            else _sse("delta", {"text": update.text})
                                        )
                                        # The SDK may close a suspended generator from another task.
                                        reset_request_context(token)
                                        token = None
                                        yield frame
                                        token = set_request_context(context)
                                if isinstance(stream, ResponseStream):
                                    await stream.get_final_response()
                                completed = True
                            finally:
                                if not completed:
                                    if token is None:
                                        token = set_request_context(context)
                                    try:
                                        await self._close_interrupted_stream(stream)
                                    except Exception:
                                        logger.exception("Failed to close interrupted Invocations agent stream")
                    if not self._legacy_wire_format:
                        session_id = partition_key[0] if isinstance(partition_key, tuple) else partition_key
                        if token is not None:
                            reset_request_context(token)
                            token = None
                        yield _sse("done", {"session_id": session_id})
                except _UnsupportedAgentOptions as exc:
                    if self._legacy_wire_format:
                        raise
                    if token is not None:
                        reset_request_context(token)
                        token = None
                    yield _sse("error", {"message": str(exc), "code": "unsupported_options", "status": 400})
                except Exception as exc:
                    logger.exception("Invocations agent stream failed")
                    if self._legacy_wire_format:
                        raise
                    message, status, code = _invocation_failure(exc)
                    if token is not None:
                        reset_request_context(token)
                        token = None
                    yield _sse("error", {"message": message, "code": code, "status": status})
                finally:
                    if token is not None:
                        reset_request_context(token)

            return _InvocationStreamingResponse(stream_response())

        try:
            lock = self._session_locks.setdefault(partition_key, asyncio.Lock())
            async with lock, self._request_agent() as agent:
                run_kwargs = self._agent_kwargs(agent, options)
                async with self._request_session(partition_key, context, hosted_scope=hosted_scope) as session:
                    response = await agent.run(parsed.messages, session=session, **run_kwargs)
            if self._legacy_wire_format:
                return Response(content=response.text)
            return JSONResponse({"response": response.text})
        except _UnsupportedAgentOptions as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception as exc:
            logger.exception("Invocations agent request failed")
            message, status, _ = _invocation_failure(exc)
            return JSONResponse({"error": message}, status_code=status)
