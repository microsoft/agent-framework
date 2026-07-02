# Copyright (c) Microsoft. All rights reserved.

"""Parsing helpers for the OpenAI Responses-API request body.

The Responses API accepts ``input`` as either a string or a list of "input
items". An item is either a content part (``input_text`` / ``input_image``
/ ``input_file``) or a message envelope ``{type: "message", role,
content: [...]}``. We translate that into an Agent Framework ``Message``
list and remap the generation-control fields the API also carries into
``ChatOptions``-shaped keys. The result is available to the channel's
``run_hook``; a default hook strips them before they reach the agent so
unknown fields from untrusted callers are not forwarded unless the host
developer explicitly opts in.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, cast

from agent_framework import AgentResponse, AgentResponseUpdate, ChatOptions, Content, Message, ResponseStream
from agent_framework_hosting import AgentRunArgs, ChannelIdentity, ChannelSession
from openai.types.responses import (
    Response as OpenAIResponse,
)
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseFunctionToolCallOutputItem,
    ResponseInputFile,
    ResponseInputImage,
    ResponseInputText,
    ResponseOutputItem,
    ResponseOutputMessage,
    ResponseOutputText,
)
from pydantic import TypeAdapter, ValidationError

_RESPONSE_OUTPUT_ITEM_ADAPTER: TypeAdapter[Any] = TypeAdapter(ResponseOutputItem)

# OpenAI Responses field name → Agent Framework ChatOptions field name.
_RESPONSES_OPTION_REMAP = {
    "max_output_tokens": "max_tokens",
    "parallel_tool_calls": "allow_multiple_tool_calls",
}
# Fields the Responses transport owns; they are consumed separately and must
# not also appear in options.
_RESPONSES_TRANSPORT_KEYS = frozenset({"input", "stream", "previous_response_id"})
_RESPONSES_RUN_TRANSPORT_KEYS = frozenset({"input", "stream", "previous_response_id", "conversation_id"})


def parse_responses_identity(body: Mapping[str, Any], channel_name: str) -> ChannelIdentity | None:
    """Surface the caller as a :class:`ChannelIdentity` so the host can record it.

    OpenAI Responses replaced ``user`` with ``safety_identifier`` — we use
    that as the native id, falling back to the legacy ``user`` field.
    """
    native = body.get("safety_identifier") or body.get("user")
    if not isinstance(native, str) or not native:
        return None
    return ChannelIdentity(channel=channel_name, native_id=native)


def _content_from_input_item(item: Mapping[str, Any]) -> Content:
    """Convert a single OpenAI Responses ``input`` item into a :class:`Content` part.

    Handles the ``input_text``/``output_text``/``text`` text variants,
    ``input_image`` URL references, and ``input_file`` references via either
    a public URL or a hosted ``file_id``. Raises ``ValueError`` for any
    unsupported item type so the surrounding parser can return a 422.
    """
    item_type = item.get("type")
    if item_type in ("input_text", "output_text", "text"):
        return Content.from_text(text=str(item.get("text", "")))
    if item_type == "input_image":
        image_url: Any = item.get("image_url")
        if isinstance(image_url, Mapping):
            image_url = cast("Mapping[str, Any]", image_url).get("url")
        if not isinstance(image_url, str):
            raise ValueError("input_image requires `image_url`")
        return Content.from_uri(uri=image_url, media_type="image/*")
    if item_type == "input_file":
        if (uri := item.get("file_url")) and isinstance(uri, str):
            return Content.from_uri(uri=uri, media_type=item.get("mime_type"))
        if file_id := item.get("file_id"):
            return Content(type="hosted_file", file_id=str(file_id))
        raise ValueError("input_file requires `file_url` or `file_id`")
    raise ValueError(f"Unsupported Responses input content type: {item_type!r}")


def messages_from_responses_input(value: Any) -> list[Message]:
    """Translate ``input`` (string or list of items) into :class:`Message` objects."""
    if isinstance(value, str):
        return [Message("user", [Content.from_text(text=value)])]
    if not isinstance(value, list) or not value:
        raise ValueError("`input` must be a non-empty string or list")

    messages: list[Message] = []
    pending_user_parts: list[Content] = []

    def flush() -> None:
        """Emit any buffered loose user content as a single user message."""
        if pending_user_parts:
            messages.append(Message("user", list(pending_user_parts)))
            pending_user_parts.clear()

    for item in cast("list[Any]", value):
        if not isinstance(item, Mapping):
            raise ValueError("each `input` item must be an object")
        item_map = cast("Mapping[str, Any]", item)
        if item_map.get("type") == "message":
            flush()
            role = str(item_map.get("role") or "user")
            content: Any = item_map.get("content") or []
            parts: list[Content]
            if isinstance(content, str):
                parts = [Content.from_text(text=content)]
            elif isinstance(content, list):
                parts = []
                for content_item in cast("list[Any]", content):
                    if not isinstance(content_item, Mapping):
                        raise ValueError("each message `content` item must be an object")
                    parts.append(_content_from_input_item(cast("Mapping[str, Any]", content_item)))
            else:
                raise ValueError("message `content` must be a string or list")
            messages.append(Message(role, parts))
        else:
            pending_user_parts.append(_content_from_input_item(item_map))

    flush()
    if not messages:
        raise ValueError("`input` produced no messages")
    return messages


def parse_responses_request(
    body: Mapping[str, Any],
) -> tuple[list[Message], dict[str, Any], ChannelSession | None]:
    """Translate a Responses-API request body into Agent Framework constructs.

    Returns a triple ``(messages, options, session)`` where:

    - ``messages`` is the parsed conversation.
    - ``options`` is a ``ChatOptions``-shaped dict with the remapped
      generation-control fields. Known Responses→ChatOptions renames are
      applied (e.g. ``max_output_tokens`` → ``max_tokens``); transport/
      session keys are excluded; ``None``-valued fields are dropped.
      Unknown fields are forwarded as-is so the channel's ``run_hook``
      can inspect and filter them. The default ``ResponsesChannel`` strips
      all options before the agent runs; supply a custom ``run_hook`` to
      selectively keep fields.
    - ``session`` is a :class:`ChannelSession` keyed by
      ``previous_response_id`` when one was supplied, else ``None``.
    """
    messages = messages_from_responses_input(body.get("input"))

    options: dict[str, Any] = {}
    for key, value in body.items():
        if key in _RESPONSES_TRANSPORT_KEYS or value is None:
            continue
        options[_RESPONSES_OPTION_REMAP.get(key, key)] = value

    session: ChannelSession | None = None
    if (prev := body.get("previous_response_id")) and isinstance(prev, str):
        session = ChannelSession(isolation_key=prev)

    return messages, options, session


def create_response_id() -> str:
    """Create a Responses-shaped response id."""
    return f"resp_{uuid.uuid4().hex}"


def responses_session_id(body: Mapping[str, Any]) -> str | None:
    """Return the Responses session id from request body, if present.

    The returned value can be a ``resp_*`` previous response id or a ``conv_*``
    conversation id. Callers choose whether this request-derived value is
    trusted for their route and deployment.

    Args:
        body: OpenAI Responses-shaped request body.

    Returns:
        Previous response id, conversation id, or ``None``.
    """
    previous_response_id = body.get("previous_response_id")
    if isinstance(previous_response_id, str) and previous_response_id:
        return previous_response_id
    conversation_id = body.get("conversation_id")
    if isinstance(conversation_id, str) and conversation_id:
        return conversation_id
    return None


def responses_to_run(body: Mapping[str, Any]) -> AgentRunArgs:
    """Convert a Responses request body into Agent Framework run values.

    Args:
        body: OpenAI Responses-shaped request body.

    Returns:
        Arguments corresponding to ``Agent.run``.

    Raises:
        ValueError: If the request body has invalid ``input``.
    """
    messages = messages_from_responses_input(body.get("input"))
    options: dict[str, Any] = {}
    for key, value in body.items():
        if key in _RESPONSES_RUN_TRANSPORT_KEYS or value is None:
            continue
        options[_RESPONSES_OPTION_REMAP.get(key, key)] = value
    return AgentRunArgs(
        messages=messages,
        options=cast("ChatOptions[Any]", options),
        stream=bool(body.get("stream", False)),
    )


def responses_from_run(
    result: AgentResponse[Any],
    *,
    response_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Convert an Agent Framework response into a Responses payload.

    Args:
        result: Agent response returned by a run.

    Keyword Args:
        response_id: Id for the response being created.
        session_id: Optional prior ``resp_*`` or ``conv_*`` session id. When it
            is a conversation id, the helper renders it in the Responses
            conversation field.

    Returns:
        Responses-compatible JSON payload.
    """
    output_items = _result_to_output_items(result, status="completed")
    response_kwargs: dict[str, Any] = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": _model_from_result(result),
        "output": output_items,
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "metadata": {},
    }
    if session_id is not None and session_id.startswith("conv_"):
        response_kwargs["conversation"] = {"id": session_id}
    return _response_payload(OpenAIResponse(**response_kwargs))


def _model_from_result(result: Any) -> str:
    model = getattr(result, "model", None)
    if isinstance(model, str) and model:
        return model
    raw = getattr(result, "raw_representation", None)
    raw_model = getattr(raw, "model", None)
    if isinstance(raw_model, str) and raw_model:
        return raw_model
    additional_properties = getattr(result, "additional_properties", None)
    if isinstance(additional_properties, Mapping):
        additional_model = cast(Mapping[str, Any], additional_properties).get("model")
        if isinstance(additional_model, str) and additional_model:
            return additional_model
    return "agent"


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
        ResponseOutputItem,
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
    item_data: dict[str, Any] = {
        "id": content.id or f"rs_{uuid.uuid4().hex}",
        "type": "reasoning",
        "summary": [],
        "status": _message_status(status),
    }
    if content.text:
        item_data["content"] = [{"type": "reasoning_text", "text": content.text}]
    if content.protected_data:
        item_data["encrypted_content"] = content.protected_data
    return _response_output_item(item_data)


def _function_call_output_item(content: Content, *, status: str) -> ResponseOutputItem:
    return cast(
        ResponseOutputItem,
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
    if content.exception:
        output: str | list[Any] = content.exception
    elif output_parts := _content_parts_to_input_items(content.items):
        output = output_parts
    elif isinstance(content.result, str):
        output = content.result
    elif content.result is None:
        output = ""
    else:
        output = json.dumps(content.result, default=str)
    return cast(
        ResponseOutputItem,
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
    output_parts: list[dict[str, Any]] = []
    outputs_value: Any = result_content.outputs if result_content is not None else content.outputs
    if isinstance(outputs_value, Sequence) and not isinstance(outputs_value, (str, bytes, bytearray)):
        for item in cast(Sequence[Any], outputs_value):
            if isinstance(item, Content) and item.type == "text":
                output_parts.append({"type": "logs", "logs": item.text or ""})
            elif isinstance(item, Content) and item.type in ("data", "uri") and item.uri:
                output_parts.append({"type": "image", "url": item.uri})

    return _response_output_item({
        "id": _content_item_id(content, result_content) or f"ci_{uuid.uuid4().hex}",
        "type": "code_interpreter_call",
        "code": _content_sequence_text(content.inputs),
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
    image_id = content.image_id or (result_content.image_id if result_content is not None else None)
    return _response_output_item({
        "id": image_id or f"ig_{uuid.uuid4().hex}",
        "type": "image_generation_call",
        "result": _image_generation_result(result_source),
        "status": _image_generation_status(status),
    })


def _mcp_call_output_item(
    content: Content,
    *,
    status: str,
    result_content: Content | None = None,
) -> ResponseOutputItem:
    return _response_output_item({
        "id": content.call_id or f"mcp_{uuid.uuid4().hex}",
        "type": "mcp_call",
        "server_label": content.server_name or "default",
        "name": content.tool_name or "tool",
        "arguments": _arguments_to_str(content.arguments),
        "output": _stringify_output(result_content.output) if result_content is not None else None,
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
        for item in cast(Sequence[Any], outputs_value):
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
            ResponseOutputItem,
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
    return (content.uri or "").startswith("data:image/")


def _image_generation_result(outputs: Any) -> str | None:
    if isinstance(outputs, Content):
        return _image_generation_content_result(outputs)
    if isinstance(outputs, Sequence) and not isinstance(outputs, (str, bytes, bytearray)):
        for output in cast(Sequence[Any], outputs):
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
        return "".join(_stringify_output(item) for item in cast(Sequence[Any], output))
    return json.dumps(output, default=str)


def _raw_response_output_item(raw: Any) -> ResponseOutputItem | None:
    if _raw_type(raw) is None:
        return None
    try:
        return cast(ResponseOutputItem, _RESPONSE_OUTPUT_ITEM_ADAPTER.validate_python(raw))
    except ValidationError:
        return None


def _response_output_item(value: Mapping[str, Any]) -> ResponseOutputItem:
    return cast(ResponseOutputItem, _RESPONSE_OUTPUT_ITEM_ADAPTER.validate_python(value))


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
        mapping_type = cast(Mapping[str, Any], raw).get("type")
        if isinstance(mapping_type, str):
            return mapping_type
    return None


def _result_to_text(result: Any) -> str:
    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text
    get_outputs = getattr(result, "get_outputs", None)
    if callable(get_outputs):
        return "".join(_output_to_text(output) for output in cast(Sequence[Any], get_outputs()))
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


def _sse_event(event_type: str, payload: Mapping[str, Any]) -> str:
    """Format one Server-Sent Event."""
    return f"event: {event_type}\ndata: {_json_dumps(payload)}\n\n"


def _json_dumps(payload: Mapping[str, Any]) -> str:
    """Serialize a Responses SSE payload."""
    return json.dumps(payload, separators=(",", ":"))


async def responses_stream_events_from_run(
    stream: ResponseStream[AgentResponseUpdate, AgentResponse[Any]],
    *,
    response_id: str,
    session_id: str | None = None,
) -> AsyncIterator[str]:
    """Convert an Agent Framework response stream into Responses SSE events.

    Args:
        stream: Agent Framework response stream returned by ``agent.run(...,
            stream=True)``.

    Keyword Args:
        response_id: Id for the response being created.
        session_id: Optional prior ``resp_*`` or ``conv_*`` session id.

    Yields:
        Server-Sent Event strings.
    """
    yield _sse_event(
        "response.created",
        {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": int(time.time()),
                "status": "in_progress",
                "model": "agent",
                "output": [],
            },
        },
    )

    async for update in stream:
        if update.text:
            yield _sse_event(
                "response.output_text.delta",
                {
                    "type": "response.output_text.delta",
                    "delta": update.text,
                },
            )

    final = await stream.get_final_response()
    yield _sse_event(
        "response.completed",
        {
            "type": "response.completed",
            "response": responses_from_run(final, response_id=response_id, session_id=session_id),
        },
    )


__all__ = [
    "create_response_id",
    "messages_from_responses_input",
    "parse_responses_identity",
    "parse_responses_request",
    "responses_from_run",
    "responses_session_id",
    "responses_stream_events_from_run",
    "responses_to_run",
]
