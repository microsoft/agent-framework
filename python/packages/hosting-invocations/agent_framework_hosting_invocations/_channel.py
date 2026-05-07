# Copyright (c) Microsoft. All rights reserved.

"""Minimal ``POST /invoke`` channel.

Inspired by ``agent-framework-foundry-hosting``'s ``InvocationsHostServer``.
A framework-agnostic surface for callers that just want to send a message and
get an answer back — no OpenAI-style envelope, no Responses item lattice.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Any, cast

from agent_framework_hosting import (
    ChannelContext,
    ChannelContribution,
    ChannelRequest,
    ChannelRunHook,
    ChannelSession,
    ChannelStreamTransformHook,
    apply_run_hook,
    logger,
)
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route


class InvocationsChannel:
    """Minimal ``POST /invoke`` surface.

    A run hook can rewrite the channel request (e.g. inject a session, add
    options) before the host invokes the agent. A stream-transform hook can
    rewrite or drop ``AgentResponseUpdate`` chunks before they hit the wire.
    """

    name = "invocations"

    def __init__(
        self,
        *,
        path: str = "/invocations",
        run_hook: ChannelRunHook | None = None,
        stream_transform_hook: ChannelStreamTransformHook | None = None,
    ) -> None:
        """Configure the invocations endpoint.

        ``path`` is the mount root the host prefixes when registering this
        channel's routes (the actual handler is ``POST {path}/invoke``).
        ``run_hook`` may rewrite the :class:`ChannelRequest` before the host
        invokes the target — typically to attach session metadata or
        translate the wire payload into ``ChatMessage`` instances.
        ``stream_transform_hook`` lets callers map or drop individual
        ``AgentResponseUpdate`` chunks while streaming.
        """
        self.path = path
        self._hook = run_hook
        self._stream_transform_hook = stream_transform_hook
        self._ctx: ChannelContext | None = None

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        """Capture the host-supplied context and register ``POST /invoke``."""
        self._ctx = context
        return ChannelContribution(routes=[Route("/invoke", self._handle, methods=["POST"])])

    async def _handle(self, request: Request) -> Response:
        """Handle a single ``POST /invoke`` call.

        Validates the JSON body shape, builds a :class:`ChannelRequest`
        (optionally with a ``ChannelSession`` keyed by ``session_id``),
        runs the configured ``run_hook``, and either streams SSE chunks
        when ``stream`` is true or returns a single JSON ``{response,
        session_id}`` envelope.
        """
        if self._ctx is None:  # pragma: no cover - guarded by Channel lifecycle
            return JSONResponse({"error": "channel not initialized"}, status_code=500)
        try:
            body: Any = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid json"}, status_code=400)

        if not isinstance(body, dict):
            return JSONResponse({"error": "request body must be an object"}, status_code=422)
        body_map: dict[str, Any] = cast("dict[str, Any]", body)

        message = body_map.get("message")
        if not isinstance(message, str) or not message:
            return JSONResponse({"error": "missing or empty 'message'"}, status_code=422)

        session_id = body_map.get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            return JSONResponse({"error": "'session_id' must be a string"}, status_code=422)

        session = ChannelSession(isolation_key=f"invocations:{session_id}") if session_id else None

        attributes: dict[str, Any] = {}
        if session_id:
            attributes["session_id"] = session_id

        channel_request = ChannelRequest(
            channel=self.name,
            operation="invoke",
            input=message,
            session=session,
            stream=bool(body_map.get("stream")),
            attributes=attributes,
        )

        if self._hook is not None:
            channel_request = await apply_run_hook(
                self._hook,
                channel_request,
                target=self._ctx.target,
                protocol_request=body_map,
            )

        if channel_request.stream:
            return StreamingResponse(
                self._stream(channel_request),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        result = await self._ctx.run(channel_request)
        return JSONResponse({"response": result.text, "session_id": session_id})

    async def _stream(self, request: ChannelRequest) -> AsyncIterator[str]:
        r"""Yield bare ``data:`` SSE lines for each text chunk + a final ``[DONE]``.

        SSE protocol notes:

        * The HTTP status is committed when ASGI sends headers, before the
          generator runs. Emitting a stream-opening 200 + ``text/event-stream``
          and signalling errors via ``event: error`` SSE frames is the
          conventional contract — ``EventSource`` and OpenAI-style SSE
          consumers treat ``event: error`` as a terminal error condition.
          Hard run-acquisition failures (e.g. target rejected) therefore
          surface as the first frame, not as an HTTP error code.
        * The SSE spec treats ``\r``, ``\n``, and ``\r\n`` as line
          terminators. Per-chunk text is split on all three so embedded
          carriage returns don't corrupt ``data:`` framing on the wire.
        """
        if self._ctx is None:  # pragma: no cover - guarded by Channel lifecycle
            yield "event: error\ndata: channel not initialized\n\n"
            return
        try:
            stream = self._ctx.run_stream(request)
            async for update in stream:
                if self._stream_transform_hook is not None:
                    transformed = self._stream_transform_hook(update)
                    if isinstance(transformed, Awaitable):
                        transformed = await transformed
                    if transformed is None:
                        continue
                    update = transformed
                chunk = getattr(update, "text", None)
                if chunk:
                    # Each text chunk is its own SSE event so curl-friendly
                    # consumers can read it directly. Newlines inside the
                    # chunk are escaped per SSE spec by emitting one
                    # ``data:`` line per source line. ``splitlines()`` is
                    # used over ``split('\n')`` so embedded ``\r`` /
                    # ``\r\n`` don't bleed into the framing.
                    for line in str(chunk).splitlines() or [""]:
                        yield f"data: {line}\n"
                    yield "\n"
            try:
                # Finalize so context-provider / history hooks on the agent
                # still run even though we are emitting our own SSE.
                # If finalization fails, the agent's persistence side
                # effects (history-provider write, context-provider hooks)
                # are unreliable — surface that to the client as an
                # ``event: error`` frame so it isn't a silent drop.
                await stream.get_final_response()
            except Exception as finalize_exc:
                logger.exception("Invocations stream finalize failed")
                yield "event: error\n"
                for line in f"finalize failed: {finalize_exc!s}".splitlines() or [""]:
                    yield f"data: {line}\n"
                yield "\n"
                return
        except Exception as exc:
            logger.exception("Invocations stream consumption failed")
            yield "event: error\n"
            for line in str(exc).splitlines() or [""]:
                yield f"data: {line}\n"
            yield "\n"
            return
        yield "data: [DONE]\n\n"


__all__ = ["InvocationsChannel"]
