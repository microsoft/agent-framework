# Copyright (c) Microsoft. All rights reserved.

"""Host session-owned agents through the Invocations protocol."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sys
import weakref
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from contextvars import Token
from copy import deepcopy
from typing import Any, cast

from agent_framework import AgentSession, RawAgent, ResponseStream, SessionStore, SupportsAgentRun
from agent_framework._telemetry import mark_feature_used
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
    InvocationStreamingResponse,
    hosted_scope,
    invocation_failure,
    partition_key,
    sse_frame,
)
from ._scope import FoundryRequestScope
from ._shared import (
    AgentSource,
    InvocationRun,
    is_agent,
    resolve_agent,
    validate_agent_background_options,
    validate_agent_source,
    validate_default_transport_options,
    validate_request_options,
    validate_sse_keep_alive_interval,
)
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


class _IncompatibleRunOptions(TypeError):
    """The agent's run method cannot accept the options returned by prepare_options."""


class InvocationsHostServer(InvocationAgentServerHost):
    """Host an agent with application-defined Invocations turns."""

    def __init__(
        self,
        agent: AgentSource[Request],
        *,
        openapi_spec: dict[str, Any] | None = None,
        agent_session_store_provider: StoreProvider[SessionStore] | None = None,
        parse_input: InvocationParser | None = None,
        prepare_options: InvocationOptionsHook | None = None,
        sse_keep_alive_interval_seconds: int | None = None,
        **agent_server_kwargs: Any,
    ) -> None:
        """Create an agent host with session-backed application turns.

        By default the host passes only the caller's message to the agent. The agent's own
        `default_options` apply unchanged, and caller-supplied options are not forwarded.
        Supply `prepare_options` to choose run options per request.

        Args:
            agent: Agent instance or sync/async factory called once per request. Factories must declare a
                required parameter named `request`, accepting the Starlette `Request` passed by keyword.
                Extra parameters must have defaults. The factory may ignore the request.
                Factories run after request parsing and option preparation. Use a factory when mutable state
                is not session-scoped. The host enters and closes factory-owned
                context-managed agents; injected instances remain application-owned. `WorkflowAgent` is
                rejected; use `InvocationsWorkflowHostServer` with a native workflow factory instead.

        Keyword Args:
            openapi_spec: Application OpenAPI specification forwarded to AgentServer.
            agent_session_store_provider: Conversation session storage. Defaults to Foundry storage when
                hosted and file-backed storage locally. Default stores expire 30 days after the last write.
            parse_input: Sync or async parser returning `InvocationRun`. Without a parser, accept JSON
                `message`, `stream`, and optional `options`. Parsed options reach the agent only through
                `prepare_options`.
            prepare_options: Sync or async hook receiving the request and a copy of the parsed caller options.
                Its returned mapping is passed to `agent.run(options=...)` and merges over the agent's
                `default_options`. Hosting rejects session, tool, middleware, and storage fields after the
                hook and before resolving the factory. A `background` value is the application's choice.
                The agent's `run` must accept `options`; otherwise the request fails with HTTP 400.
            sse_keep_alive_interval_seconds: Positive streaming heartbeat interval. If omitted, use a positive
                `SSE_KEEPALIVE_INTERVAL`, otherwise disable heartbeats. Not a request/model timeout.
            **agent_server_kwargs: Additional AgentServer SDK constructor arguments, such as
                `asyncapi_spec_json` and `asyncapi_spec_yaml`.

        Raises:
            TypeError: If the agent source, parser/hook, or heartbeat type is invalid.
            ValueError: If the heartbeat interval is nonpositive or an injected agent has unsupported
                background or transport defaults.
        """
        validate_sse_keep_alive_interval(sse_keep_alive_interval_seconds)
        validate_agent_source(agent)
        if parse_input is not None and not callable(parse_input):
            raise TypeError("parse_input must be a callable.")
        if prepare_options is not None and not callable(prepare_options):
            raise TypeError("prepare_options must be a callable.")
        if is_agent(agent):
            self._validate_agent_options(agent)
        super().__init__(openapi_spec=openapi_spec, **agent_server_kwargs)
        if sse_keep_alive_interval_seconds is not None:
            self.config.sse_keepalive_interval = sse_keep_alive_interval_seconds
        self._agent = agent
        self._owns_request_agent = not is_agent(agent)
        self._parse_input = parse_input
        self._prepare_options = prepare_options
        self._session_store_provider = (
            AgentSessionStoreProvider(store_name="invocation_sessions")
            if agent_session_store_provider is None
            else agent_session_store_provider
        )
        self._session_locks: weakref.WeakValueDictionary[str | tuple[str, str], asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self.invoke_handler(self._handle_invoke)
        mark_feature_used(FeatureIndex.FOUNDRY_HOSTING)

    def _partition_key(
        self,
        *,
        context: FoundryAgentRequestContext | None = None,
        scope: FoundryRequestScope | None = None,
    ) -> str | tuple[str, str]:
        """Get the session partition key for the current request."""
        return partition_key(self.config, get_request_context() if context is None else context, scope)

    @asynccontextmanager
    async def _request_agent(self, request: Request) -> AsyncGenerator[SupportsAgentRun]:
        agent = await resolve_agent(self._agent, request)
        self._validate_agent_options(agent)
        async with AsyncExitStack() as resources:
            if self._owns_request_agent and isinstance(agent, AbstractAsyncContextManager):
                await resources.enter_async_context(agent)
            yield agent

    @staticmethod
    def _validate_agent_options(agent: SupportsAgentRun) -> None:
        validate_agent_background_options(agent, provider_background=False)
        if isinstance(agent, RawAgent):
            validate_default_transport_options(agent.default_options, allow_agent_store=True)

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
        if self._parse_input is not None:
            result = self._parse_input(request)
            parsed = await result if inspect.isawaitable(result) else result
            if not isinstance(parsed, InvocationRun):
                raise TypeError("parse_input must return InvocationRun.")
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
        if self._prepare_options is None:
            return {}
        result = self._prepare_options(request, deepcopy(dict(parsed.options)))
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, Mapping) or any(not isinstance(key, str) for key in result):
            raise TypeError("prepare_options must return a mapping of MAF run options with string keys.")
        options = deepcopy(dict(result))
        reserved = _AGENT_CONTROLLED_FIELDS.intersection(options)
        if reserved:
            raise ValueError(f"Invocations options cannot set agent-controlled fields: {', '.join(sorted(reserved))}.")
        validate_request_options(options, allow_background=True)
        return options

    @staticmethod
    def _agent_kwargs(agent: SupportsAgentRun, options: dict[str, Any]) -> dict[str, Any]:
        if not options:
            return {}
        try:
            inspect.signature(agent.run).bind_partial(options=options)
        except (TypeError, ValueError):
            raise _IncompatibleRunOptions(
                "The hosted agent does not accept the run options returned by prepare_options."
            ) from None
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
        """Invoke the configured agent with a trusted request."""
        context = get_request_context()
        try:
            request_scope = hosted_scope(self.config, request, context) if self.config.is_hosted else None
            key = partition_key(self.config, context, request_scope)
        except RuntimeError as exc:
            logger.error("Failed to resolve Invocations session: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

        try:
            parsed = await self._parse(request)
            options = await self._options(request, parsed)
            if is_agent(self._agent):
                self._agent_kwargs(self._agent, options)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception:
            logger.exception("Failed to prepare Invocations request")
            return JSONResponse({"error": "Failed to prepare invocation request."}, status_code=500)

        if parsed.stream:

            async def stream_response() -> AsyncGenerator[str]:
                token: Token[FoundryAgentRequestContext] | None = set_request_context(context)
                try:
                    lock = self._session_locks.setdefault(key, asyncio.Lock())
                    async with lock, self._request_agent(request) as agent:
                        run_kwargs = self._agent_kwargs(agent, options)
                        async with self._request_session(key, context, hosted_scope=request_scope) as session:
                            stream = agent.run(parsed.messages, session=session, stream=True, **run_kwargs)
                            completed = False
                            try:
                                async for update in stream:
                                    if update.text:
                                        # The SDK may close a suspended generator from another task.
                                        reset_request_context(token)
                                        token = None
                                        yield sse_frame("delta", {"text": update.text})
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
                    session_id = key[0] if isinstance(key, tuple) else key
                    if token is not None:
                        reset_request_context(token)
                        token = None
                    yield sse_frame("done", {"session_id": session_id})
                except _IncompatibleRunOptions as exc:
                    if token is not None:
                        reset_request_context(token)
                        token = None
                    yield sse_frame("error", {"message": str(exc), "code": "invalid_request", "status": 400})
                except Exception as exc:
                    logger.exception("Invocations agent stream failed")
                    message, status, code = invocation_failure(exc)
                    if token is not None:
                        reset_request_context(token)
                        token = None
                    yield sse_frame("error", {"message": message, "code": code, "status": status})
                finally:
                    if token is not None:
                        reset_request_context(token)

            return InvocationStreamingResponse(stream_response())

        try:
            lock = self._session_locks.setdefault(key, asyncio.Lock())
            async with lock, self._request_agent(request) as agent:
                run_kwargs = self._agent_kwargs(agent, options)
                async with self._request_session(key, context, hosted_scope=request_scope) as session:
                    response = await agent.run(parsed.messages, session=session, **run_kwargs)
            return JSONResponse({"response": response.text})
        except _IncompatibleRunOptions as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception as exc:
            logger.exception("Invocations agent request failed")
            message, status, _ = invocation_failure(exc)
            return JSONResponse({"error": message}, status_code=status)
