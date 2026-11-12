# Copyright (c) Microsoft. All rights reserved.

"""Host session-owned agents through the Invocations protocol."""

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
from typing import Any, Literal, cast

from agent_framework import AgentSession, ResponseStream, SessionStore, SupportsAgentRun
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
    InvocationOptionsHook,
    _invocation_failure,  # pyright: ignore[reportPrivateUsage]
    _InvocationStreamingResponse,  # pyright: ignore[reportPrivateUsage]
    _sse,  # pyright: ignore[reportPrivateUsage]
    invocation_partition_key,
    invocation_request_scope,
)
from ._scope import FoundryRequestScope
from ._shared import (
    AgentSessionStoreProvider,
    AgentSource,
    InvocationRun,
    StoreProvider,
    UnsupportedOptions,
    is_agent,
    resolve_agent,
    validate_agent_source,
    validate_request_options,
    validate_sse_keep_alive_interval,
    validate_unsupported_options,
)

logger = logging.getLogger(__name__)

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


class InvocationsHostServer(InvocationAgentServerHost):
    """Host an agent with application-defined Invocations turns."""

    def __init__(
        self,
        agent: AgentSource[Request],
        *,
        openapi_spec: dict[str, Any] | None = None,
        agent_session_store_provider: StoreProvider[SessionStore] | None = None,
        parse_input: Callable[[Request], InvocationRun | Awaitable[InvocationRun]] | None = None,
        prepare_options: InvocationOptionsHook | None = None,
        unsupported_options: UnsupportedOptions = "warn",
        legacy_wire_format: bool = False,
        sse_keep_alive_interval_seconds: int | None = None,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
        agent_server_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        """Create an agent host with session-backed application turns.

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
                `message`, optional `options`, and `stream`.
            prepare_options: Sync or async hook receiving the request and a copy of caller generation
                options. Return the replacement mapping; hosting validates it before agent dispatch.
            unsupported_options: Policy for agents without runtime options: `"warn"`, `"ignore"`, or `"error"`.
            legacy_wire_format: Deprecated agent-only plain-text and raw-stream compatibility format.
                Heartbeats are disabled in this format.
            sse_keep_alive_interval_seconds: Positive streaming heartbeat interval in seconds.
                `None` inherits a positive `SSE_KEEPALIVE_INTERVAL`, otherwise heartbeats are disabled.
                Zero and negative explicit values are invalid. This is not a request or inference timeout.
                An explicit interval cannot be combined with `legacy_wire_format=True`.
            log_level: Logging level forwarded unchanged to AgentServer. `None` preserves the SDK default.
            agent_server_kwargs: Caller-owned settings expanded into the AgentServer SDK constructor.
                Hosting does not validate their contents or mutate the mapping. SDK errors propagate.

        Raises:
            TypeError: If the agent source, parser/hook, heartbeat type, or legacy-format flag is invalid.
            ValueError: If the heartbeat interval is nonpositive, raw legacy output requests heartbeats,
                or the unsupported-options policy is invalid.
        """
        validate_agent_source(agent)
        if parse_input is not None and not callable(parse_input):
            raise TypeError("parse_input must be a callable.")
        if prepare_options is not None and not callable(prepare_options):
            raise TypeError("prepare_options must be a callable.")
        if not isinstance(legacy_wire_format, bool):
            raise TypeError("legacy_wire_format must be a boolean.")
        validate_sse_keep_alive_interval(sse_keep_alive_interval_seconds)
        if legacy_wire_format and sse_keep_alive_interval_seconds is not None:
            raise ValueError("SSE heartbeats require framed SSE; disable legacy_wire_format.")
        unsupported_options = validate_unsupported_options(unsupported_options)
        super().__init__(
            openapi_spec=openapi_spec,
            log_level=log_level,
            **({} if agent_server_kwargs is None else agent_server_kwargs),
        )
        if legacy_wire_format:
            self.config.sse_keepalive_interval = 0
        elif sse_keep_alive_interval_seconds is not None:
            self.config.sse_keepalive_interval = sse_keep_alive_interval_seconds
        self._agent = agent
        self._owns_request_agent = not is_agent(agent)
        self._parse_input = parse_input
        self._prepare_options = prepare_options
        self._unsupported_options = unsupported_options
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

    @asynccontextmanager
    async def _request_agent(self, request: Request) -> AsyncGenerator[SupportsAgentRun]:
        agent = await resolve_agent(self._agent, request)
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
        """Invoke the configured agent with a trusted request."""
        context = get_request_context()
        try:
            hosted_scope = invocation_request_scope(self.config, request, context)
            partition_key = invocation_partition_key(self.config, context=context, scope=hosted_scope)
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
                    async with lock, self._request_agent(request) as agent:
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
            async with lock, self._request_agent(request) as agent:
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
