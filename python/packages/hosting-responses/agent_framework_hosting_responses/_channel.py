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

import json
import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any, cast

from agent_framework_hosting import (
    ChannelContext,
    ChannelContribution,
    ChannelRequest,
    ChannelResponseHook,
    ChannelRunHook,
    ChannelSession,
    ChannelStreamUpdateHook,
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
    parse_responses_identity,
    parse_responses_request,
)


class ResponsesChannel:
    """Minimal OpenAI-Responses-shaped surface.

    Mounts one ``POST`` route at ``path``. The default path is ``/responses``;
    use ``path=""`` to expose the route at the app root.
    """

    name = "responses"

    def __init__(
        self,
        *,
        path: str = "/responses",
        run_hook: ChannelRunHook | None = None,
        response_hook: ChannelResponseHook | None = None,
        stream_update_hook: ChannelStreamUpdateHook | None = None,
        response_id_factory: Callable[..., str] | None = None,
    ) -> None:
        """Create a Responses channel.

        Keyword Args:
            path: Endpoint path on the host. Default ``"/responses"`` matches
                the upstream OpenAI surface; use ``""`` to expose this channel
                at the app root.
            run_hook: Optional :data:`ChannelRunHook` the host invokes with
                the parsed :class:`ChannelRequest` before the agent target
                runs. May return a replacement request.
            response_hook: Optional :data:`ChannelResponseHook` the host invokes
                before the channel serializes an originating
                :class:`HostedRunResult` into a Responses envelope.
            stream_update_hook: Optional per-update hook
                applied while streaming Server-Sent Events. Return a
                replacement update, or ``None`` to drop the update.
            response_id_factory: Optional callable that mints the
                per-request response id. Default produces
                ``resp_<uuid hex>`` which matches the OpenAI Responses
                wire shape. Override when the host backing storage
                requires a different id format.
                The same id is used for the channel envelope and for
                the host-side anchoring (``ChannelRequest.attributes``)
                so storage and replay agree.

                Security note on partition co-location: when a caller
                supplies ``previous_response_id`` we forward it to the
                factory so id backends that embed partition keys can
                co-locate the new record with the chain's existing
                partition. The factory passes that hint through to the
                storage layer; ownership and authorization are enforced by
                that storage layer, not by this channel.
        """
        self.path = path
        self._hook = run_hook
        self.response_hook = response_hook
        self._stream_update_hook = stream_update_hook
        self._ctx: ChannelContext | None = None
        self._response_id_factory: Callable[..., str] = (
            response_id_factory if response_id_factory is not None else (lambda *_a, **_kw: f"resp_{uuid.uuid4().hex}")
        )

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        """Capture the host-supplied context and register the endpoint route."""
        self._ctx = context
        return ChannelContribution(routes=[Route("/", self._handle, methods=["POST"])])

    async def _handle(self, request: Request) -> Response:
        """Handle a single Responses API call.

        Parses the OpenAI Responses-shaped body into ``Message`` /
        ``options`` / ``ChannelSession`` triples via :mod:`._parsing`,
        applies the optional ``run_hook``, and either streams an SSE
        response stream or returns a one-shot OpenAI ``Response`` envelope.
        """
        if self._ctx is None:  # pragma: no cover - guarded by Channel lifecycle
            return JSONResponse({"error": "channel not initialized"}, status_code=500)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid json"}, status_code=400)
        if not isinstance(body, Mapping):
            return JSONResponse({"error": "request body must be a JSON object"}, status_code=422)
        body = cast("Mapping[str, Any]", body)

        try:
            messages, options, session = parse_responses_request(body)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

        # Mint the response id once per request so the channel envelope
        # (one-shot or streamed) and any host-side anchoring (e.g. the
        # context providers that bind ``response_id``) agree on the same
        # handle. The next turn arrives with this value as
        # ``previous_response_id`` and the storage chain walks. We pass
        # both anchors via ``ChannelRequest.attributes`` so the host
        # can pick them up without a channel-specific contract.
        previous_response_id: str | None = None
        prev_raw = body.get("previous_response_id")
        if isinstance(prev_raw, str) and prev_raw:
            previous_response_id = prev_raw
        # Pass the previous id (if any) as a hint to the factory so id
        # backends that embed partition keys can co-locate the new record
        # with the chain's existing partition.
        # No-arg factories continue to work via ``Callable[..., str]``.
        response_id = self._response_id_factory(previous_response_id)
        if session is None:
            session = ChannelSession(isolation_key=response_id)

        attributes: dict[str, Any] = {"response_id": response_id}
        if previous_response_id is not None:
            attributes["previous_response_id"] = previous_response_id

        # Honor the OpenAI-Responses ``stream`` flag — non-streaming by
        # default, SSE when the caller opts in. The channel chooses the
        # transport before run hooks execute.
        channel_request = ChannelRequest(
            channel=self.name,
            operation="message.create",
            input=messages,
            session=session,
            options=options or None,
            stream=bool(body.get("stream", False)),
            identity=parse_responses_identity(body, self.name),
            attributes=attributes,
        )

        if channel_request.stream:
            return StreamingResponse(
                self._stream_events(channel_request, body, response_id=response_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        result = await self._ctx.run(
            channel_request,
            run_hook=self._hook,
            protocol_request=body,
            response_hook=self.response_hook,
            channel_name=self.name,
        )
        text = _result_to_text(result.result)
        envelope = self._build_response(body, text, status="completed", response_id=response_id)
        return JSONResponse(_response_payload(envelope))

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
        model = body.get("model")
        return OpenAIResponse(
            id=response_id or self._response_id_factory(None),
            object="response",
            created_at=int(time.time()),
            status=status,  # type: ignore[arg-type]
            model=model if isinstance(model, str) and model else "agent",
            output=[
                ResponseOutputMessage(
                    id=f"msg_{uuid.uuid4().hex}",
                    type="message",
                    role="assistant",
                    status=message_status,
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
            return f"event: {event.type}\ndata: {_event_json(event)}\n\n"

        skeleton = self._build_response(body, "", status="in_progress", response_id=response_id)
        yield sse(ResponseCreatedEvent(type="response.created", response=skeleton, sequence_number=next_seq()))

        accumulated = ""
        try:
            stream = await self._ctx.run_stream(
                request,
                run_hook=self._hook,
                protocol_request=body,
                stream_update_hook=self._stream_update_hook,
                response_hook=self.response_hook,
                channel_name=self.name,
            )
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
                final_response = await stream.get_final_response()
            except Exception:  # pragma: no cover - finalize is best-effort
                logger.exception("Responses stream finalize failed")
                final_response = None
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

        completed_text = _result_to_text(final_response) if final_response is not None else accumulated
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


def _result_to_text(result: Any) -> str:
    """Render an agent or workflow result to plain text for Responses JSON."""
    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text
    get_outputs = getattr(result, "get_outputs", None)
    if callable(get_outputs):
        return "".join(_output_to_text(output) for output in cast("Sequence[Any]", get_outputs()))
    return str(result)


def _output_to_text(output: Any) -> str:
    text = getattr(output, "text", None)
    if isinstance(text, str):
        return text
    return str(output)


def _response_payload(response: OpenAIResponse) -> dict[str, Any]:
    payload = response.model_dump(mode="json", exclude_none=True)
    created_at = payload.get("created_at")
    if isinstance(created_at, float):
        payload["created_at"] = int(created_at)
    return payload


def _event_json(event: Any) -> str:
    payload = cast("dict[str, Any]", event.model_dump(mode="json", exclude_none=True))
    response = cast("dict[str, Any] | None", payload.get("response"))
    if isinstance(response, dict) and isinstance(response.get("created_at"), float):
        response["created_at"] = int(response["created_at"])
    return json.dumps(payload, separators=(",", ":"))


__all__ = ["ResponsesChannel"]
