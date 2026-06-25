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

import dataclasses
import json
import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any, cast

from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message, ResponseStream
from agent_framework_hosting import (
    ChannelContext,
    ChannelContribution,
    ChannelRequest,
    ChannelResponseHook,
    ChannelRunHook,
    ChannelSession,
    ChannelStreamUpdateHook,
    get_current_isolation_keys,
    logger,
)
from openai.types.responses import (
    Response as OpenAIResponse,
)
from openai.types.responses import (
    ResponseCodeInterpreterCallCodeDeltaEvent,
    ResponseCodeInterpreterCallCodeDoneEvent,
    ResponseCodeInterpreterToolCall,
    ResponseCompletedEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreatedEvent,
    ResponseError,
    ResponseFailedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseFunctionToolCall,
    ResponseFunctionToolCallOutputItem,
    ResponseInputFile,
    ResponseInputImage,
    ResponseInputText,
    ResponseMcpCallArgumentsDeltaEvent,
    ResponseMcpCallArgumentsDoneEvent,
    ResponseOutputItem,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
    ResponseReasoningTextDeltaEvent,
    ResponseReasoningTextDoneEvent,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
)
from openai.types.responses.response_output_item import McpCall
from pydantic import TypeAdapter, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from ._parsing import (
    parse_responses_identity,
    parse_responses_request,
)

_RESPONSE_OUTPUT_ITEM_ADAPTER: TypeAdapter[Any] = TypeAdapter(ResponseOutputItem)


def _strip_options_hook(request: ChannelRequest, **_: Any) -> ChannelRequest:
    """Default run hook: remove all parsed options before reaching the agent.

    Parsed options (e.g. ``temperature``, ``instructions``) are available to
    a custom ``run_hook`` via ``request.options`` and the raw body via
    ``protocol_request``.  This default prevents untrusted callers from
    injecting generation parameters when no custom hook is configured.
    Host developers who want to forward specific options should supply their
    own ``run_hook`` instead of this default.
    """
    return dataclasses.replace(request, options=None)


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
                the OpenAI surface; use ``""`` to expose this channel
                at the app root.
            run_hook: Optional :data:`ChannelRunHook` the host invokes with
                the parsed :class:`ChannelRequest` before the agent target
                runs. May return a replacement request.

                By default the channel strips all parsed options before
                forwarding the request so callers cannot inject generation
                parameters (``temperature``, ``instructions``, etc.) unless
                the host explicitly allows it.  Supplying a custom hook
                **replaces** that default entirely — the hook receives the
                full ``ChannelRequest`` (with ``options`` populated from the
                parsed body) and the raw ``protocol_request``, and is
                responsible for deciding what to forward to the agent.
            response_hook: Optional :data:`ChannelResponseHook` the host invokes
                before the channel serializes an originating
                :class:`HostedRunResult` into a Responses envelope.
            stream_update_hook: Optional per-update hook
                applied while streaming Server-Sent Events.
                The callable should return a replacement update,
                or ``None`` to drop the update.
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

                Security note on partition co-location: when a caller
                supplies ``previous_response_id`` we forward it to the
                factory so id backends that embed partition keys can
                co-locate the new record with the chain's existing
                partition. The factory passes that hint through to the
                storage layer; **partition ownership is enforced at
                the storage layer**, not in the channel. Channel-level
                forwarding is therefore a performance hint, not a
                security boundary; the host's isolation middleware
                must establish the caller's identity before this
                route is entered.
        """
        self.path = path
        self._hook: ChannelRunHook = run_hook if run_hook is not None else _strip_options_hook
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

        # When no ``previous_response_id`` chain anchor is on the body,
        # surface any isolation key the **host** lifted from the request
        # context as the channel session id. Some environments provide
        # isolation through trusted headers, while other channels derive
        # it from body fields, paths, channel-native metadata, or even
        # environment-provided context in an ephemeral host. This fallback
        # only covers the host-context case; explicit protocol anchors
        # still win.
        #
        # Security note: we consume the host-bound contextvar set by the
        # ASGI isolation middleware, NOT the raw header off the wire.
        # That middleware is the operator's place to enforce auth and
        # gate which callers get to set isolation. If you mount the host
        # in front of a custom auth boundary, your middleware should
        # validate the caller before stamping ``set_current_isolation_keys``;
        # never trust raw wire headers to identify a session bucket.
        # A host-provided isolation key need not be a storage anchor:
        # multi-turn storage chaining still goes through the
        # ``previous_response_id`` / bound ``response_id`` pair on
        # ``ChannelRequest.attributes``.
        bound_keys = get_current_isolation_keys()
        chat_iso = bound_keys.chat_key if bound_keys is not None else None
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
        output = _result_to_output_items(result.result, status="completed")
        envelope = self._build_response(body, output, status="completed", response_id=response_id)
        return JSONResponse(_response_payload(envelope))

    def _build_response(
        self,
        body: Mapping[str, Any],
        output: Sequence[ResponseOutputItem],
        *,
        status: str,
        response_id: str | None = None,
        output_message_id: str | None = None,
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
        output_items = list(output)
        if output_message_id is not None:
            for output_item in output_items:
                if isinstance(output_item, ResponseOutputMessage):
                    output_item.id = output_message_id
                    break
        model = body.get("model")
        return OpenAIResponse(
            id=response_id or self._response_id_factory(None),
            object="response",
            created_at=int(time.time()),
            status=status,  # type: ignore[arg-type]
            model=model if isinstance(model, str) and model else "agent",
            output=output_items,
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

        skeleton = self._build_response(
            body,
            _text_output_items("", status="in_progress", message_id=msg_id),
            status="in_progress",
            response_id=response_id,
        )
        yield _sse_event(ResponseCreatedEvent(type="response.created", response=skeleton, sequence_number=next_seq()))

        next_output_index = 1
        update_stream: ResponseStream[AgentResponseUpdate, list[ResponseOutputItem]] | None = None
        try:
            stream = await self._ctx.run_stream(
                request,
                run_hook=self._hook,
                protocol_request=body,
                stream_update_hook=self._stream_update_hook,
                response_hook=self.response_hook,
                channel_name=self.name,
            )

            def update_to_events(update: AgentResponseUpdate) -> list[Any]:
                nonlocal next_output_index
                events: list[Any] = []
                for content in update.contents:
                    content_events, uses_output_index = _content_to_stream_events(
                        content,
                        message_id=msg_id,
                        output_index=next_output_index,
                        next_sequence_number=next_seq,
                    )
                    events.extend(content_events)
                    if uses_output_index:
                        next_output_index += 1
                return events

            update_stream = ResponseStream(
                stream,
                finalizer=lambda updates: _streamed_updates_output(
                    updates,
                    status="completed",
                    message_id=msg_id,
                ),
            )
            event_stream = update_stream.flat_map(update_to_events, finalizer=lambda _events: None)

            async for event in event_stream:
                yield _sse_event(event)
            try:
                # Finalize so context-provider / history hooks on the agent
                # still run even though we are emitting our own SSE.
                final_response = await stream.get_final_response()
            except Exception:  # pragma: no cover - finalize is best-effort
                logger.exception("Responses stream finalize failed")
                final_response = None
        except Exception as exc:
            logger.exception("Responses stream consumption failed")
            failed_output = (
                _streamed_updates_output(update_stream.updates, status="failed", message_id=msg_id)
                if update_stream is not None
                else _text_output_items("", status="failed", message_id=msg_id)
            )
            failed = self._build_response(
                body,
                failed_output,
                status="failed",
                response_id=response_id,
            )
            failed.error = ResponseError(code="server_error", message=str(exc))
            yield _sse_event(
                ResponseFailedEvent(
                    type="response.failed",
                    response=failed,
                    sequence_number=next_seq(),
                )
            )
            return

        completed = self._build_response(
            body,
            _result_to_output_items(final_response, status="completed")
            if final_response is not None
            else await update_stream.get_final_response(),
            status="completed",
            response_id=response_id,
            output_message_id=msg_id,
        )
        yield _sse_event(
            ResponseCompletedEvent(
                type="response.completed",
                response=completed,
                sequence_number=next_seq(),
            )
        )


def _sse_event(event: Any) -> str:
    return f"event: {event.type}\ndata: {_event_json(event)}\n\n"


def _content_to_stream_events(
    content: Content,
    *,
    message_id: str,
    output_index: int,
    next_sequence_number: Callable[[], int],
) -> tuple[list[Any], bool]:
    events: list[Any] = []

    def add_start(item: ResponseOutputItem) -> None:
        events.append(
            ResponseOutputItemAddedEvent(
                type="response.output_item.added",
                item=item,
                output_index=output_index,
                sequence_number=next_sequence_number(),
            )
        )

    def add_done(item: ResponseOutputItem) -> None:
        events.append(
            ResponseOutputItemDoneEvent(
                type="response.output_item.done",
                item=item,
                output_index=output_index,
                sequence_number=next_sequence_number(),
            )
        )

    def add_item(item: ResponseOutputItem, *, added_item: ResponseOutputItem | None = None) -> None:
        add_start(added_item or item)
        add_done(item)

    raw_item = _raw_response_output_item(content.raw_representation)
    if raw_item is not None:
        add_item(raw_item)
        return events, not isinstance(raw_item, ResponseOutputMessage)

    match content.type:
        case "text":
            text_part = ResponseOutputText(type="output_text", text=content.text or "", annotations=[])
            added_part = ResponseOutputText(type="output_text", text="", annotations=[])
            output_item = ResponseOutputMessage(
                id=message_id,
                type="message",
                role="assistant",
                status="completed",
                content=[text_part],
            )
            events.append(
                ResponseOutputItemAddedEvent(
                    type="response.output_item.added",
                    item=ResponseOutputMessage(
                        id=message_id,
                        type="message",
                        role="assistant",
                        status="in_progress",
                        content=[],
                    ),
                    output_index=0,
                    sequence_number=next_sequence_number(),
                )
            )
            events.append(
                ResponseContentPartAddedEvent(
                    type="response.content_part.added",
                    item_id=message_id,
                    output_index=0,
                    content_index=0,
                    part=added_part,
                    sequence_number=next_sequence_number(),
                )
            )
            if text_part.text:
                events.append(
                    ResponseTextDeltaEvent(
                        type="response.output_text.delta",
                        item_id=message_id,
                        output_index=0,
                        content_index=0,
                        delta=text_part.text,
                        logprobs=[],
                        sequence_number=next_sequence_number(),
                    )
                )
                events.append(
                    ResponseTextDoneEvent(
                        type="response.output_text.done",
                        item_id=message_id,
                        output_index=0,
                        content_index=0,
                        text=text_part.text,
                        logprobs=[],
                        sequence_number=next_sequence_number(),
                    )
                )
            events.append(
                ResponseContentPartDoneEvent(
                    type="response.content_part.done",
                    item_id=message_id,
                    output_index=0,
                    content_index=0,
                    part=text_part,
                    sequence_number=next_sequence_number(),
                )
            )
            events.append(
                ResponseOutputItemDoneEvent(
                    type="response.output_item.done",
                    item=output_item,
                    output_index=0,
                    sequence_number=next_sequence_number(),
                )
            )
            return events, False

        case "text_reasoning":
            reasoning_id = content.id or f"rs_{uuid.uuid4().hex}"
            text = content.text or ""
            output_item = _reasoning_output_item(content, status="completed")
            add_start(
                ResponseReasoningItem(
                    id=reasoning_id,
                    type="reasoning",
                    summary=[],
                    content=[],
                    status="in_progress",
                )
            )
            if text:
                events.append(
                    ResponseReasoningTextDeltaEvent(
                        type="response.reasoning_text.delta",
                        item_id=reasoning_id,
                        output_index=output_index,
                        content_index=0,
                        delta=text,
                        sequence_number=next_sequence_number(),
                    ),
                )
                events.append(
                    ResponseReasoningTextDoneEvent(
                        type="response.reasoning_text.done",
                        item_id=reasoning_id,
                        output_index=output_index,
                        content_index=0,
                        text=text,
                        sequence_number=next_sequence_number(),
                    ),
                )
            add_done(output_item)
            return events, True

        case "function_call":
            output_item = _function_call_output_item(content, status="completed")
            if not isinstance(output_item, ResponseFunctionToolCall):
                add_item(output_item)
                return events, True
            add_start(
                ResponseFunctionToolCall(
                    id=output_item.id,
                    type="function_call",
                    call_id=output_item.call_id,
                    name=output_item.name,
                    arguments="",
                    status="in_progress",
                )
            )
            if output_item.arguments:
                item_id = output_item.id or output_item.call_id
                events.append(
                    ResponseFunctionCallArgumentsDeltaEvent(
                        type="response.function_call_arguments.delta",
                        item_id=item_id,
                        output_index=output_index,
                        delta=output_item.arguments,
                        sequence_number=next_sequence_number(),
                    ),
                )
                events.append(
                    ResponseFunctionCallArgumentsDoneEvent(
                        type="response.function_call_arguments.done",
                        item_id=item_id,
                        output_index=output_index,
                        arguments=output_item.arguments,
                        name=output_item.name,
                        sequence_number=next_sequence_number(),
                    ),
                )
            add_done(output_item)
            return events, True

        case "mcp_server_tool_call":
            output_item = _mcp_call_output_item(content, status="completed")
            if not isinstance(output_item, McpCall):
                add_item(output_item)
                return events, True
            add_start(
                McpCall(
                    id=output_item.id,
                    type="mcp_call",
                    server_label=output_item.server_label,
                    name=output_item.name,
                    arguments="",
                    status="in_progress",
                )
            )
            if output_item.arguments:
                events.append(
                    ResponseMcpCallArgumentsDeltaEvent(
                        type="response.mcp_call_arguments.delta",
                        item_id=output_item.id,
                        output_index=output_index,
                        delta=output_item.arguments,
                        sequence_number=next_sequence_number(),
                    ),
                )
                events.append(
                    ResponseMcpCallArgumentsDoneEvent(
                        type="response.mcp_call_arguments.done",
                        item_id=output_item.id,
                        output_index=output_index,
                        arguments=output_item.arguments,
                        sequence_number=next_sequence_number(),
                    ),
                )
            add_done(output_item)
            return events, True

        case "code_interpreter_tool_call" | "code_interpreter_tool_result":
            output_item = _code_interpreter_output_item(content, status="completed")
            if not isinstance(output_item, ResponseCodeInterpreterToolCall):
                add_item(output_item)
                return events, True
            add_start(
                ResponseCodeInterpreterToolCall(
                    id=output_item.id,
                    type="code_interpreter_call",
                    container_id=output_item.container_id,
                    code="",
                    outputs=None,
                    status="in_progress",
                )
            )
            if output_item.code:
                events.append(
                    ResponseCodeInterpreterCallCodeDeltaEvent(
                        type="response.code_interpreter_call_code.delta",
                        item_id=output_item.id,
                        output_index=output_index,
                        delta=output_item.code,
                        sequence_number=next_sequence_number(),
                    ),
                )
                events.append(
                    ResponseCodeInterpreterCallCodeDoneEvent(
                        type="response.code_interpreter_call_code.done",
                        item_id=output_item.id,
                        output_index=output_index,
                        code=output_item.code,
                        sequence_number=next_sequence_number(),
                    ),
                )
            add_done(output_item)
            return events, True

        case "function_result":
            add_item(_function_result_output_item(content, status="completed"))
            return events, True

        case "image_generation_tool_call" | "image_generation_tool_result":
            add_item(_image_generation_output_item(content, status="completed"))
            return events, True

        case "mcp_server_tool_result":
            add_item(_mcp_result_output_item(content, status="completed"))
            return events, True

        case "shell_tool_call":
            add_item(_shell_call_output_item(content, status="completed"))
            return events, True

        case "shell_tool_result":
            add_item(_shell_result_output_item(content, status="completed"))
            return events, True

        case "function_approval_request":
            add_item(_function_approval_request_output_item(content))
            return events, True

        case "function_approval_response":
            add_item(_function_approval_response_output_item(content))
            return events, True

        case "data" | "uri" | "hosted_file":
            add_item(_media_content_output_item(content, status="completed"))
            return events, True

        case "error":
            error_text = str(content)
            text_content = Content.from_text(error_text)
            return _content_to_stream_events(
                text_content,
                message_id=message_id,
                output_index=output_index,
                next_sequence_number=next_sequence_number,
            )

        case _:
            return [], False


def _streamed_updates_output(
    updates: Sequence[AgentResponseUpdate],
    *,
    status: str,
    message_id: str,
) -> list[ResponseOutputItem]:
    if not updates:
        return _text_output_items("", status=status, message_id=message_id)
    output_items = _result_to_output_items(AgentResponse.from_updates(updates), status=status)
    for output_item in output_items:
        if isinstance(output_item, ResponseOutputMessage):
            output_item.id = message_id
            break
    return output_items


def _result_to_output_items(result: Any, *, status: str) -> list[ResponseOutputItem]:
    """Render an agent or workflow result as Responses output items."""
    messages = getattr(result, "messages", None)
    if isinstance(messages, Sequence) and not isinstance(messages, (str, bytes, bytearray)):
        return _messages_to_output_items(cast("Sequence[Any]", messages), status=status)

    if isinstance(result, Message):
        return _messages_to_output_items([result], status=status)
    if isinstance(result, Content):
        return _contents_to_output_items([result], status=status)

    get_outputs = getattr(result, "get_outputs", None)
    if callable(get_outputs):
        output_items: list[ResponseOutputItem] = []
        for output in cast("Sequence[Any]", get_outputs()):
            output_items.extend(_output_to_output_items(output, status=status))
        return output_items

    text = getattr(result, "text", None)
    if isinstance(text, str):
        return _text_output_items(text, status=status)
    return _text_output_items(_result_to_text(result), status=status)


def _output_to_output_items(output: Any, *, status: str) -> list[ResponseOutputItem]:
    if isinstance(output, Message):
        return _messages_to_output_items([output], status=status)
    if isinstance(output, Content):
        return _contents_to_output_items([output], status=status)
    messages = getattr(output, "messages", None)
    if isinstance(messages, Sequence) and not isinstance(messages, (str, bytes, bytearray)):
        return _messages_to_output_items(cast("Sequence[Any]", messages), status=status)
    text = getattr(output, "text", None)
    if isinstance(text, str):
        return _text_output_items(text, status=status)
    return _text_output_items(str(output), status=status)


def _messages_to_output_items(messages: Sequence[Any], *, status: str) -> list[ResponseOutputItem]:
    output_items: list[ResponseOutputItem] = []
    message_contents: list[Content] = []

    for message in messages:
        if not isinstance(message, Message):
            if message_contents:
                output_items.extend(_contents_to_output_items(message_contents, status=status))
                message_contents.clear()
            output_items.extend(_output_to_output_items(message, status=status))
            continue
        message_contents.extend(message.contents)

    if message_contents:
        output_items.extend(_contents_to_output_items(message_contents, status=status))

    return output_items


def _contents_to_output_items(
    contents: Sequence[Content],
    *,
    status: str,
    seen_raw_items: dict[tuple[str, str], int] | None = None,
) -> list[ResponseOutputItem]:
    output_items: list[ResponseOutputItem] = []
    message_content: list[Any] = []
    seen: dict[tuple[str, str], int] = seen_raw_items if seen_raw_items is not None else {}

    def flush_message() -> None:
        if not message_content:
            return
        output_items.append(_message_output_item(message_content, status=status))
        message_content.clear()

    content_list = list(contents)
    index = 0
    while index < len(content_list):
        content = content_list[index]
        raw_item = _raw_response_output_item(content.raw_representation)
        if raw_item is not None:
            raw_key = _response_output_item_key(raw_item)
            if raw_key in seen:
                output_items[seen[raw_key]] = raw_item
            else:
                flush_message()
                seen[raw_key] = len(output_items)
                output_items.append(raw_item)
            index += 1
            continue

        next_content = content_list[index + 1] if index + 1 < len(content_list) else None
        if _is_matching_code_interpreter_result(content, next_content):
            flush_message()
            output_items.append(_code_interpreter_output_item(content, status=status, result_content=next_content))
            index += 2
            continue
        if _is_matching_image_generation_result(content, next_content):
            flush_message()
            output_items.append(_image_generation_output_item(content, status=status, result_content=next_content))
            index += 2
            continue
        if _is_matching_mcp_result(content, next_content):
            flush_message()
            output_items.append(_mcp_call_output_item(content, status=status, result_content=next_content))
            index += 2
            continue

        match content.type:
            case "text":
                message_content.append(_message_text_content(content))
            case "text_reasoning":
                flush_message()
                output_items.append(_reasoning_output_item(content, status=status))
            case "function_call":
                flush_message()
                output_items.append(_function_call_output_item(content, status=status))
            case "function_result":
                flush_message()
                output_items.append(_function_result_output_item(content, status=status))
            case "code_interpreter_tool_call" | "code_interpreter_tool_result":
                flush_message()
                output_items.append(_code_interpreter_output_item(content, status=status))
            case "image_generation_tool_call" | "image_generation_tool_result":
                flush_message()
                output_items.append(_image_generation_output_item(content, status=status))
            case "mcp_server_tool_call":
                flush_message()
                output_items.append(_mcp_call_output_item(content, status=status))
            case "mcp_server_tool_result":
                flush_message()
                output_items.append(_mcp_result_output_item(content, status=status))
            case "shell_tool_call":
                flush_message()
                output_items.append(_shell_call_output_item(content, status=status))
            case "shell_tool_result":
                flush_message()
                output_items.append(_shell_result_output_item(content, status=status))
            case "function_approval_request":
                flush_message()
                output_items.append(_function_approval_request_output_item(content))
            case "function_approval_response":
                flush_message()
                output_items.append(_function_approval_response_output_item(content))
            case "data" | "uri" | "hosted_file":
                flush_message()
                output_items.append(_media_content_output_item(content, status=status))
            case "error":
                message_content.append(ResponseOutputText(type="output_text", text=str(content), annotations=[]))
            case _:
                flush_message()
                output_items.extend(_text_output_items(json.dumps(content.to_dict(), default=str), status=status))
        index += 1

    flush_message()
    return output_items


def _is_matching_code_interpreter_result(content: Content, next_content: Content | None) -> bool:
    return (
        content.type == "code_interpreter_tool_call"
        and next_content is not None
        and next_content.type == "code_interpreter_tool_result"
        and content.call_id == next_content.call_id
    )


def _is_matching_image_generation_result(content: Content, next_content: Content | None) -> bool:
    return (
        content.type == "image_generation_tool_call"
        and next_content is not None
        and next_content.type == "image_generation_tool_result"
        and content.image_id == next_content.image_id
    )


def _is_matching_mcp_result(content: Content, next_content: Content | None) -> bool:
    return (
        content.type == "mcp_server_tool_call"
        and next_content is not None
        and next_content.type == "mcp_server_tool_result"
        and content.call_id == next_content.call_id
    )


def _message_status(status: str) -> str:
    return status if status in ("in_progress", "completed", "incomplete") else "incomplete"


def _text_output_items(text: str, *, status: str, message_id: str | None = None) -> list[ResponseOutputItem]:
    return [
        _message_output_item(
            [ResponseOutputText(type="output_text", text=text, annotations=[])],
            status=status,
            message_id=message_id,
        )
    ]


def _message_output_item(content: Sequence[Any], *, status: str, message_id: str | None = None) -> ResponseOutputItem:
    return cast(
        "ResponseOutputItem",
        ResponseOutputMessage(
            id=message_id or f"msg_{uuid.uuid4().hex}",
            type="message",
            role="assistant",
            status=_message_status(status),  # type: ignore[arg-type]
            content=list(content),
        ),
    )


def _message_text_content(content: Content) -> Any:
    raw_type = _raw_type(content.raw_representation)
    if raw_type in ("output_text", "refusal"):
        return content.raw_representation
    return ResponseOutputText(type="output_text", text=content.text or "", annotations=[])


def _reasoning_output_item(content: Content, *, status: str) -> ResponseOutputItem:
    reasoning_text = content.text or ""
    item_id = content.id or f"rs_{uuid.uuid4().hex}"
    item_data: dict[str, Any] = {
        "id": item_id,
        "type": "reasoning",
        "summary": [],
        "status": _message_status(status),
    }
    if reasoning_text:
        item_data["content"] = [{"type": "reasoning_text", "text": reasoning_text}]
    if content.protected_data:
        item_data["encrypted_content"] = content.protected_data
    return _response_output_item(item_data)


def _function_call_output_item(content: Content, *, status: str) -> ResponseOutputItem:
    return cast(
        "ResponseOutputItem",
        ResponseFunctionToolCall(
            id=content.additional_properties.get("fc_id") if content.additional_properties else None,
            type="function_call",
            call_id=content.call_id or f"call_{uuid.uuid4().hex}",
            name=content.name or "tool",
            arguments=_arguments_to_str(content.arguments),
            status=_message_status(status),  # type: ignore[arg-type]
        ),
    )


def _function_result_output_item(content: Content, *, status: str) -> ResponseOutputItem:
    output: str | list[Any]
    if content.exception:
        output = content.exception
    elif output_parts := _content_parts_to_input_items(content.items):
        output = output_parts
    elif isinstance(content.result, str):
        output = content.result
    elif content.result is None:
        output = ""
    else:
        output = json.dumps(content.result, default=str)
    return cast(
        "ResponseOutputItem",
        ResponseFunctionToolCallOutputItem(
            id=f"fcout_{uuid.uuid4().hex}",
            type="function_call_output",
            call_id=content.call_id or f"call_{uuid.uuid4().hex}",
            output=output,
            status=_message_status(status),  # type: ignore[arg-type]
        ),
    )


def _code_interpreter_output_item(
    content: Content,
    *,
    status: str,
    result_content: Content | None = None,
) -> ResponseOutputItem:
    code = _content_sequence_text(content.inputs)
    output_parts: list[dict[str, Any]] = []
    outputs_value: Any = result_content.outputs if result_content is not None else content.outputs
    if isinstance(outputs_value, Sequence) and not isinstance(outputs_value, (str, bytes, bytearray)):
        for item in cast("Sequence[Any]", outputs_value):
            if not isinstance(item, Content):
                continue
            if item.type == "text":
                output_parts.append({"type": "logs", "logs": item.text or ""})
            elif item.type in ("data", "uri") and item.uri:
                output_parts.append({"type": "image", "url": item.uri})

    return _response_output_item({
        "id": _content_item_id(content, result_content) or f"ci_{uuid.uuid4().hex}",
        "type": "code_interpreter_call",
        "code": code,
        "container_id": str(_content_property(content, result_content, "container_id") or "agent_framework"),
        "outputs": output_parts or None,
        "status": _code_interpreter_status(status),
    })


def _image_generation_output_item(
    content: Content,
    *,
    status: str,
    result_content: Content | None = None,
) -> ResponseOutputItem:
    result_source = result_content.outputs if result_content is not None else content.outputs
    result = _image_generation_result(result_source)
    image_id = content.image_id or (result_content.image_id if result_content is not None else None)
    return _response_output_item({
        "id": image_id or f"ig_{uuid.uuid4().hex}",
        "type": "image_generation_call",
        "result": result,
        "status": _image_generation_status(status),
    })


def _mcp_call_output_item(
    content: Content,
    *,
    status: str,
    result_content: Content | None = None,
) -> ResponseOutputItem:
    output = _stringify_output(result_content.output) if result_content is not None else None
    return _response_output_item({
        "id": content.call_id or f"mcp_{uuid.uuid4().hex}",
        "type": "mcp_call",
        "server_label": content.server_name or "default",
        "name": content.tool_name or "tool",
        "arguments": _arguments_to_str(content.arguments),
        "output": output,
        "status": _mcp_status(status),
    })


def _mcp_result_output_item(content: Content, *, status: str) -> ResponseOutputItem:
    return _response_output_item({
        "id": content.call_id or f"mcp_{uuid.uuid4().hex}",
        "type": "mcp_call",
        "server_label": content.server_name or "default",
        "name": content.tool_name or "tool",
        "arguments": "",
        "output": _stringify_output(content.output),
        "status": _mcp_status(status),
    })


def _shell_call_output_item(content: Content, *, status: str) -> ResponseOutputItem:
    return _response_output_item({
        "id": content.additional_properties.get("item_id") or f"shell_{uuid.uuid4().hex}",
        "type": "shell_call",
        "call_id": content.call_id or f"call_{uuid.uuid4().hex}",
        "action": {
            "commands": content.commands or [],
            "timeout_ms": content.timeout_ms,
            "max_output_length": content.max_output_length,
        },
        "environment": {"type": "local"},
        "status": _message_status(status),
    })


def _shell_result_output_item(content: Content, *, status: str) -> ResponseOutputItem:
    outputs: list[dict[str, Any]] = []
    outputs_value: Any = content.outputs
    if isinstance(outputs_value, Sequence) and not isinstance(outputs_value, (str, bytes, bytearray)):
        for item in cast("Sequence[Any]", outputs_value):
            if not isinstance(item, Content):
                continue
            outcome = {"type": "timeout"} if item.timed_out else {"type": "exit", "exit_code": item.exit_code or 0}
            outputs.append({"stdout": item.stdout or "", "stderr": item.stderr or "", "outcome": outcome})

    return _response_output_item({
        "id": content.additional_properties.get("item_id") or f"shellout_{uuid.uuid4().hex}",
        "type": "shell_call_output",
        "call_id": content.call_id or f"call_{uuid.uuid4().hex}",
        "output": outputs,
        "max_output_length": content.max_output_length,
        "status": _message_status(status),
    })


def _function_approval_request_output_item(content: Content) -> ResponseOutputItem:
    function_call = content.function_call
    return _response_output_item({
        "id": content.id or f"approval_{uuid.uuid4().hex}",
        "type": "mcp_approval_request",
        "server_label": (
            function_call.additional_properties.get("server_label", "agent_framework")
            if function_call is not None
            else "agent_framework"
        ),
        "name": function_call.name if function_call is not None and function_call.name else "tool",
        "arguments": _arguments_to_str(function_call.arguments if function_call is not None else None),
    })


def _function_approval_response_output_item(content: Content) -> ResponseOutputItem:
    return _response_output_item({
        "id": content.id or f"approval_{uuid.uuid4().hex}",
        "type": "mcp_approval_response",
        "approval_request_id": content.id or "",
        "approve": bool(content.approved),
    })


def _media_content_output_item(content: Content, *, status: str) -> ResponseOutputItem:
    parts = _content_parts_to_input_items([content])
    if parts:
        return cast(
            "ResponseOutputItem",
            ResponseFunctionToolCallOutputItem(
                id=f"content_{uuid.uuid4().hex}",
                type="function_call_output",
                call_id=f"content_{uuid.uuid4().hex}",
                output=parts,
                status=_message_status(status),  # type: ignore[arg-type]
            ),
        )
    return _text_output_items(json.dumps(content.to_dict(), default=str), status=status)[0]


def _content_parts_to_input_items(contents: Sequence[Content] | None) -> list[Any]:
    if not contents:
        return []

    parts: list[Any] = []
    for content in contents:
        match content.type:
            case "text":
                parts.append(ResponseInputText(type="input_text", text=content.text or ""))
            case "data" | "uri":
                if not content.uri:
                    continue
                if _is_image_content(content):
                    parts.append(ResponseInputImage(type="input_image", image_url=content.uri, detail="auto"))
                else:
                    parts.append(ResponseInputFile(type="input_file", file_url=content.uri))
            case "hosted_file":
                if content.file_id:
                    parts.append(ResponseInputFile(type="input_file", file_id=content.file_id))
            case _:
                parts.append(ResponseInputText(type="input_text", text=json.dumps(content.to_dict(), default=str)))
    return parts


def _content_sequence_text(contents: Sequence[Content] | None) -> str | None:
    if not contents:
        return None
    text = "".join(content.text or "" for content in contents if content.type == "text")
    return text or None


def _is_image_content(content: Content) -> bool:
    media_type = content.media_type or ""
    if media_type.startswith("image/"):
        return True
    uri = content.uri or ""
    return uri.startswith("data:image/")


def _image_generation_result(outputs: Any) -> str | None:
    if isinstance(outputs, Content):
        return _image_generation_content_result(outputs)
    if isinstance(outputs, Sequence) and not isinstance(outputs, (str, bytes, bytearray)):
        for output in cast("Sequence[Any]", outputs):
            if isinstance(output, Content) and (result := _image_generation_content_result(output)):
                return result
    if isinstance(outputs, str):
        return outputs
    return None


def _image_generation_content_result(content: Content) -> str | None:
    uri = content.uri
    if not uri:
        return None
    if ";base64," in uri:
        return uri.split(";base64,", 1)[1]
    return uri


def _content_item_id(content: Content, result_content: Content | None = None) -> str | None:
    item_id = content.additional_properties.get("item_id")
    if isinstance(item_id, str) and item_id:
        return item_id
    if result_content is not None:
        result_item_id = result_content.additional_properties.get("item_id")
        if isinstance(result_item_id, str) and result_item_id:
            return result_item_id
    return content.call_id or (result_content.call_id if result_content is not None else None)


def _content_property(content: Content, result_content: Content | None, key: str) -> Any:
    if key in content.additional_properties:
        return content.additional_properties[key]
    if result_content is not None and key in result_content.additional_properties:
        return result_content.additional_properties[key]
    return None


def _code_interpreter_status(status: str) -> str:
    if status in ("in_progress", "completed", "incomplete", "failed"):
        return status
    return "incomplete"


def _image_generation_status(status: str) -> str:
    if status in ("in_progress", "completed", "failed"):
        return status
    return "failed"


def _mcp_status(status: str) -> str:
    if status in ("in_progress", "completed", "incomplete", "failed"):
        return status
    return "incomplete"


def _arguments_to_str(arguments: Any | None) -> str:
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments, default=str)


def _stringify_output(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, Sequence) and not isinstance(output, (str, bytes, bytearray)):
        parts: list[str] = []
        for item in cast("Sequence[Any]", output):
            if isinstance(item, Content) and item.type == "text":
                parts.append(item.text or "")
            else:
                parts.append(_stringify_output(item))
        return "".join(parts)
    return json.dumps(output, default=str)


def _raw_response_output_item(raw: Any) -> ResponseOutputItem | None:
    if _raw_type(raw) is None:
        return None
    try:
        return cast("ResponseOutputItem", _RESPONSE_OUTPUT_ITEM_ADAPTER.validate_python(raw))
    except ValidationError:
        return None


def _response_output_item(value: Mapping[str, Any]) -> ResponseOutputItem:
    return cast("ResponseOutputItem", _RESPONSE_OUTPUT_ITEM_ADAPTER.validate_python(value))


def _response_output_item_key(item: ResponseOutputItem) -> tuple[str, str]:
    item_type = _raw_type(item) or "unknown"
    item_id = getattr(item, "id", None) or getattr(item, "call_id", None)
    if isinstance(item_id, str) and item_id:
        return item_type, item_id
    return item_type, str(id(item))


def _raw_type(raw: Any) -> str | None:
    raw_type = getattr(raw, "type", None)
    if isinstance(raw_type, str):
        return raw_type
    if isinstance(raw, Mapping):
        raw_mapping = cast("Mapping[str, Any]", raw)
        mapping_type = raw_mapping.get("type")
        if isinstance(mapping_type, str):
            return mapping_type
    return None


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
