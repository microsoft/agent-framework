# Copyright (c) Microsoft. All rights reserved.

"""``ResponsesChannel`` — OpenAI Responses-shaped HTTP surface.

Exposes a single ``POST /responses`` endpoint that accepts
``{"input": "...", "stream": false}`` (and the rest of the Responses API
request body) and returns either a Responses-shaped JSON body
(``stream=False``, default) or a Server-Sent-Events stream
(``stream=True``).

Payload construction reuses the ``openai.types.responses`` Pydantic
models so the OpenAI Python SDK ``stream=True`` consumer parses every
required field without surprises.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from agent_framework_hosting import (
    ChannelContext,
    ChannelContribution,
    ChannelRequest,
    ChannelRunHook,
    ChannelSession,
    DeliveryReport,
    HostedRunResult,
    apply_run_hook,
    logger,
)
from openai.types.responses import (
    Response as OpenAIResponse,
)
from openai.types.responses import (
    ResponseCompletedEvent,
    ResponseCreatedEvent,
    ResponseError,
    ResponseFailedEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
)
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from ._parsing import (
    parse_response_target,
    parse_responses_identity,
    parse_responses_request,
)


def _ack_text(report: DeliveryReport) -> str:
    """Tiny acknowledgement string for the originating wire.

    Used when the agent reply is delivered out-of-band via :class:`ChannelPush`.
    """
    pushed = ", ".join(report.pushed) if report.pushed else "(none)"
    return f"[delivered out-of-band → {pushed}]"


class ResponsesChannel:
    """Minimal OpenAI-Responses-shaped surface.

    Mounts ``POST <path>/responses`` (default path ``/responses`` so the
    full route is ``/responses/responses`` when the channel is prefixed,
    or just ``/responses`` when ``path=""``).
    """

    name = "responses"

    def __init__(
        self,
        *,
        path: str = "",
        run_hook: ChannelRunHook | None = None,
        response_id_factory: Callable[..., str] | None = None,
    ) -> None:
        """Create a Responses channel.

        Args:
            path: Mount prefix on the host. Default ``""`` mounts the
                ``POST /responses`` route at the app root, matching the
                upstream OpenAI surface.
            run_hook: Optional :data:`ChannelRunHook` invoked with the
                parsed :class:`ChannelRequest` before the agent target
                runs. May return a replacement request.
            response_id_factory: Optional callable that mints the
                per-request response id. Default produces
                ``resp_<uuid hex>`` which matches the OpenAI Responses
                wire shape. Override when the host backing storage
                requires a different id format (e.g. Foundry storage,
                whose partition keys are encoded in the id and which
                rejects free-form ``resp_*`` ids with a server error).
                The same id is used for the channel envelope and for
                the host-side anchoring (``ChannelRequest.attributes``)
                so storage and replay agree.
        """
        self.path = path
        self._hook = run_hook
        self._ctx: ChannelContext | None = None
        self._response_id_factory: Callable[..., str] = (
            response_id_factory if response_id_factory is not None else (lambda *_a, **_kw: f"resp_{uuid.uuid4().hex}")
        )

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        """Capture the host-supplied context and register ``POST /responses``."""
        self._ctx = context
        return ChannelContribution(routes=[Route("/responses", self._handle, methods=["POST"])])

    async def _handle(self, request: Request) -> Response:
        """Handle a single ``POST /responses`` call.

        Parses the OpenAI Responses-shaped body into ``ChatMessage`` /
        ``options`` / ``ChannelSession`` triples via :mod:`._parsing`,
        applies the optional ``run_hook``, and either streams an SSE
        response stream or returns a one-shot OpenAI ``Response`` envelope.
        Non-originating ``response_target`` values resolve to a delivery
        acknowledgement instead of echoing the agent text on this wire.
        """
        if self._ctx is None:  # pragma: no cover - guarded by Channel lifecycle
            return JSONResponse({"error": "channel not initialized"}, status_code=500)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid json"}, status_code=400)

        try:
            messages, options, session = parse_responses_request(body)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

        # When no ``previous_response_id`` chain anchor is on the body,
        # surface the platform-injected ``x-agent-chat-isolation-key`` as
        # the channel session so callers without an explicit anchor still
        # get a stable per-conversation session id (used by non-Foundry
        # history providers, routing/idempotency, etc.). The chat-iso
        # value is *not* a valid storage anchor; the Foundry history
        # provider deliberately ignores it — multi-turn storage chaining
        # goes through the ``previous_response_id`` / bound
        # ``response_id`` pair on ``ChannelRequest.attributes``. The
        # user-iso companion header is consumed at the host level by
        # ``_FoundryIsolationASGIMiddleware`` so the channel never has
        # to import Foundry-specific types.
        chat_iso = request.headers.get("x-agent-chat-isolation-key")
        if session is None and chat_iso:
            session = ChannelSession(isolation_key=chat_iso)

        # Mint the response id once per request so the channel envelope
        # (one-shot or streamed) and any host-side anchoring (e.g. the
        # Foundry history provider's ``bind_request_context``) agree on
        # the same handle. The next turn arrives with this value as
        # ``previous_response_id`` and the storage chain walks. We pass
        # both anchors via ``ChannelRequest.attributes`` so the host
        # can pick them up without a channel-specific contract.
        previous_response_id: str | None = None
        prev_raw = body.get("previous_response_id")
        if isinstance(prev_raw, str) and prev_raw:
            previous_response_id = prev_raw
        # Pass the previous id (if any) as a hint to the factory so id
        # backends that embed partition keys (e.g. Foundry storage) can
        # co-locate the new record with the chain's existing partition.
        # No-arg factories continue to work via ``Callable[..., str]``.
        response_id = self._response_id_factory(previous_response_id)

        attributes: dict[str, Any] = {"response_id": response_id}
        if previous_response_id is not None:
            attributes["previous_response_id"] = previous_response_id

        # Honor the OpenAI-Responses ``stream`` flag — non-streaming by
        # default, SSE when the caller opts in. Run hooks may still flip
        # this per-request (e.g. force non-streaming for a particular user).
        channel_request = ChannelRequest(
            channel=self.name,
            operation="message.create",
            input=messages,
            session=session,
            options=options or None,
            stream=bool(body.get("stream", False)),
            identity=parse_responses_identity(body, self.name),
            response_target=parse_response_target(body),
            attributes=attributes,
        )

        if self._hook is not None:
            channel_request = await apply_run_hook(
                self._hook,
                channel_request,
                target=self._ctx.target,
                protocol_request=body,
            )

        if channel_request.stream:
            return StreamingResponse(
                self._stream_events(channel_request, body, response_id=response_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        result = await self._ctx.run(channel_request)
        report = await self._ctx.deliver_response(channel_request, result)
        text = result.text if report.include_originating else _ack_text(report)
        envelope = self._build_response(body, text, status="completed", response_id=response_id)
        return JSONResponse(envelope.model_dump(mode="json", exclude_none=True))

    def _build_response(
        self,
        body: Mapping[str, Any],
        text: str,
        *,
        status: str,
        response_id: str | None = None,
    ) -> OpenAIResponse:
        """Construct an OpenAI ``Response`` for a finished (non-streaming) run.

        ``status`` mirrors the top-level Response status set values
        (``in_progress`` / ``completed`` / ``failed`` / ``incomplete`` /
        ``cancelled``). The nested ``ResponseOutputMessage.status`` field
        only accepts ``in_progress`` / ``completed`` / ``incomplete``, so
        terminal-but-non-success states collapse to ``incomplete`` there
        — the failure detail still travels via the top-level ``status``
        and (for streamed errors) the ``error`` field.

        ``response_id``: the per-request id minted in :meth:`_handle`.
        Passed in so envelope and storage agree on a single handle per
        turn (see :meth:`_handle` notes). Falls back to a fresh uuid
        when callers (e.g. :meth:`_stream_events`'s skeleton path
        before this argument was introduced) don't supply one.
        """
        message_status = status if status in ("in_progress", "completed", "incomplete") else "incomplete"
        return OpenAIResponse(
            id=response_id or self._response_id_factory(None),
            object="response",
            created_at=time.time(),
            status=status,  # type: ignore[arg-type]
            model=body.get("model", "agent"),
            output=[
                ResponseOutputMessage(
                    id=f"msg_{uuid.uuid4().hex}",
                    type="message",
                    role="assistant",
                    status=message_status,  # type: ignore[arg-type]
                    content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
                )
            ],
            parallel_tool_calls=False,
            tool_choice="auto",
            tools=[],
            metadata={},
        )

    async def _stream_events(
        self,
        request: ChannelRequest,
        body: Mapping[str, Any],
        *,
        response_id: str,
    ) -> AsyncIterator[str]:
        """Yield SSE events shaped like the OpenAI Responses streaming protocol.

        Emits ``response.created`` → many ``response.output_text.delta``
        → ``response.completed`` (or ``response.failed`` on error).
        """
        if self._ctx is None:  # pragma: no cover - guarded by Channel lifecycle
            return

        msg_id = f"msg_{uuid.uuid4().hex}"
        seq = 0

        def next_seq() -> int:
            nonlocal seq
            seq += 1
            return seq

        def sse(event: Any) -> str:
            return f"event: {event.type}\ndata: {event.model_dump_json(exclude_none=True)}\n\n"

        skeleton = self._build_response(body, "", status="in_progress", response_id=response_id)
        yield sse(ResponseCreatedEvent(type="response.created", response=skeleton, sequence_number=next_seq()))

        accumulated = ""
        try:
            stream = self._ctx.run_stream(request)
            async for update in stream:
                chunk = getattr(update, "text", None)
                if chunk:
                    accumulated += chunk
                    yield sse(
                        ResponseTextDeltaEvent(
                            type="response.output_text.delta",
                            item_id=msg_id,
                            output_index=0,
                            content_index=0,
                            delta=chunk,
                            logprobs=[],
                            sequence_number=next_seq(),
                        )
                    )
            try:
                # Finalize so context-provider / history hooks on the agent
                # still run even though we are emitting our own SSE.
                await stream.get_final_response()
            except Exception:  # pragma: no cover - finalize is best-effort
                logger.exception("Responses stream finalize failed")
        except Exception as exc:
            logger.exception("Responses stream consumption failed")
            failed = self._build_response(body, accumulated, status="failed", response_id=response_id)
            failed.error = ResponseError(code="server_error", message=str(exc))
            yield sse(
                ResponseFailedEvent(
                    type="response.failed",
                    response=failed,
                    sequence_number=next_seq(),
                )
            )
            return

        completed_text = accumulated
        report = await self._ctx.deliver_response(request, HostedRunResult(text=accumulated))
        if not report.include_originating:
            completed_text = _ack_text(report)
        completed = self._build_response(body, completed_text, status="completed", response_id=response_id)
        # Reuse the same message id we emitted deltas under.
        if completed.output and isinstance(completed.output[0], ResponseOutputMessage):
            completed.output[0].id = msg_id
        yield sse(
            ResponseCompletedEvent(
                type="response.completed",
                response=completed,
                sequence_number=next_seq(),
            )
        )


__all__ = ["ResponsesChannel"]
