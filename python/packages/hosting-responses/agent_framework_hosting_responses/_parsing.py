# Copyright (c) Microsoft. All rights reserved.

"""Parsing helpers for the OpenAI Responses-API request body.

The Responses API accepts ``input`` as either a string or a list of "input
items". An item is either a content part (``input_text`` / ``input_image``
/ ``input_file``) or a message envelope ``{type: "message", role,
content: [...]}``. We translate that into an Agent Framework ``Message``
list and remap the generation-control fields the API also carries into
``ChatOptions``-shaped keys. App-owned route code decides which options to
pass through to ``agent.run(...)`` and which request-owned fields to drop.
"""

from __future__ import annotations

import json
import time
import uuid
import warnings
from collections.abc import AsyncIterator, Iterator, Mapping, MutableMapping, Sequence
from copy import copy
from typing import Any, Literal, cast

from agent_framework import AgentResponse, AgentResponseUpdate, ChatOptions, Content, Message, ResponseStream
from agent_framework._telemetry import mark_feature_used
from agent_framework_hosting import AgentRunArgs
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
    ResponseOutputRefusal,
    ResponseOutputText,
)
from openai.types.responses.response_usage import ResponseUsage
from pydantic import TypeAdapter, ValidationError

from ._feature_usage import FeatureIndex

_MODEL_OUTPUT_KIND_KEY = "model_output_kind"
_MODEL_OUTPUT_REFUSAL = "refusal"
_RESPONSE_OUTPUT_ITEM_ADAPTER: TypeAdapter[Any] = TypeAdapter(ResponseOutputItem)
_RESPONSE_USAGE_ADAPTER: TypeAdapter[Any] = TypeAdapter(ResponseUsage)

# OpenAI Responses field name → Agent Framework ChatOptions field name.
_RESPONSES_OPTION_REMAP = {
    "max_output_tokens": "max_tokens",
    "parallel_tool_calls": "allow_multiple_tool_calls",
}
# Fields the Responses transport owns; they are consumed separately and must
# not also appear in options.
_RESPONSES_RUN_TRANSPORT_KEYS = frozenset({
    "input",
    "stream",
    "previous_response_id",
    "conversation",
    "conversation_id",
})
_RESPONSES_CONTINUATION_KEYS = ("previous_response_id", "conversation", "conversation_id")
_RESPONSES_INPUT_MESSAGE_ROLES = frozenset({"user", "assistant", "system", "developer"})
_RESPONSES_STATUSES = frozenset({"completed", "failed", "in_progress", "cancelled", "queued", "incomplete"})
_STREAMING_TERMINAL_STATUSES = frozenset({"completed", "failed", "incomplete"})


def _is_refusal_text_content(content: Content) -> bool:
    return content.type == "text" and content.additional_properties.get(_MODEL_OUTPUT_KIND_KEY) == _MODEL_OUTPUT_REFUSAL


def _code_interpreter_projection_key(content: Content) -> tuple[str, str] | None:
    if content.type not in {"code_interpreter_tool_call", "code_interpreter_tool_result"}:
        return None
    call_id = content.call_id or content.additional_properties.get("item_id")
    if not isinstance(call_id, str) or not call_id:
        return None
    return content.type, call_id


def _content_from_input_item(item: Mapping[str, Any]) -> Content:
    """Convert a single OpenAI Responses ``input`` item into a :class:`Content` part.

    Handles the ``input_text``/``output_text``/``text`` text variants,
    ``input_image`` URL references, and ``input_file`` references via either
    a public URL or a hosted ``file_id``. Raises ``ValueError`` for any
    unsupported item type so the surrounding parser can return a 422.
    """
    item_type = item.get("type")
    if item_type in ("input_text", "output_text", "text"):
        text = item.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError(f"{item_type} requires a non-empty string `text`")
        return Content.from_text(text=text)
    if item_type == "refusal":
        refusal = item.get("refusal")
        if not isinstance(refusal, str) or not refusal:
            raise ValueError("refusal requires a non-empty string `refusal`")
        return Content.from_text(
            text=refusal,
            additional_properties={_MODEL_OUTPUT_KIND_KEY: _MODEL_OUTPUT_REFUSAL},
        )
    if item_type == "input_image":
        image_url: Any = item.get("image_url")
        if isinstance(image_url, Mapping):
            image_url = cast("Mapping[str, Any]", image_url).get("url")
        if not isinstance(image_url, str) or not image_url:
            raise ValueError("input_image requires a non-empty string `image_url`")
        return Content.from_uri(uri=image_url, media_type="image/*")
    if item_type == "input_file":
        file_url = item.get("file_url")
        if file_url is not None:
            if not isinstance(file_url, str) or not file_url:
                raise ValueError("input_file `file_url` must be a non-empty string")
            return Content.from_uri(uri=file_url, media_type=item.get("mime_type"))
        file_id = item.get("file_id")
        if file_id is not None:
            if not isinstance(file_id, str) or not file_id:
                raise ValueError("input_file `file_id` must be a non-empty string")
            return Content(type="hosted_file", file_id=file_id)
        raise ValueError("input_file requires a non-empty string `file_url` or `file_id`")
    raise ValueError(f"Unsupported Responses input content type: {item_type!r}")


def messages_from_responses_input(value: Any) -> list[Message]:
    """Translate ``input`` (string or list of items) into :class:`Message` objects."""
    if isinstance(value, str):
        if not value:
            raise ValueError("`input` must be a non-empty string or list")
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
            role = item_map.get("role")
            if not isinstance(role, str) or role not in _RESPONSES_INPUT_MESSAGE_ROLES:
                raise ValueError("message `role` must be one of `user`, `assistant`, `system`, or `developer`")
            if "content" not in item_map:
                raise ValueError("message requires non-empty `content`")
            content: Any = item_map["content"]
            parts: list[Content]
            if isinstance(content, str):
                if not content:
                    raise ValueError("message `content` must not be empty")
                parts = [Content.from_text(text=content)]
            elif isinstance(content, list):
                if not content:
                    raise ValueError("message `content` must not be empty")
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


def create_response_id() -> str:
    """Create a Responses-shaped response id."""
    return f"resp_{uuid.uuid4().hex}"


def create_conversation_id() -> str:
    """Create a Responses-shaped conversation id."""
    return f"conv_{uuid.uuid4().hex}"


def responses_session_id(body: Mapping[str, Any]) -> tuple[str, bool] | tuple[None, None]:
    """Return the Responses session id and whether it is a conversation id.

    The session id can be a ``resp_*`` previous response id or a ``conv_*``
    conversation id. Callers choose whether these request-derived values are
    trusted for their route and deployment.

    Args:
        body: OpenAI Responses-shaped request body.

    Returns:
        The session id, if present, and whether it came from ``conversation``.
        The flag is ``None`` when no session id is present.

    Raises:
        ValueError: If a continuation field is malformed or conflicts with
            another continuation mechanism.
    """
    return _responses_session_id(body, warn=True)


def _responses_session_id(
    body: Mapping[str, Any],
    *,
    warn: bool,
) -> tuple[str, bool] | tuple[None, None]:
    supplied_keys = [key for key in _RESPONSES_CONTINUATION_KEYS if body.get(key) is not None]
    if len(supplied_keys) > 1:
        raise ValueError("`previous_response_id`, `conversation`, and `conversation_id` are mutually exclusive")
    if not supplied_keys:
        return None, None

    key = supplied_keys[0]
    value = body[key]
    if key == "previous_response_id":
        if not isinstance(value, str) or not value:
            raise ValueError("`previous_response_id` must be a non-empty string")
        if warn and not value.startswith("resp_"):
            warnings.warn(
                "`previous_response_id` does not use the OpenAI Responses `resp_` prefix; "
                "continuing with the supplied value.",
                UserWarning,
                stacklevel=3,
            )
        return value, False

    if key == "conversation":
        if isinstance(value, Mapping):
            value = cast("Mapping[str, Any]", value).get("id")
        if not isinstance(value, str) or not value:
            raise ValueError("`conversation` must be a non-empty string or an object with a non-empty string `id`")
    else:
        if not isinstance(value, str) or not value:
            raise ValueError("`conversation_id` must be a non-empty string")
        if warn:
            warnings.warn(
                "`conversation_id` is deprecated; use the OpenAI Responses `conversation` field instead.",
                DeprecationWarning,
                stacklevel=3,
            )

    if warn and not value.startswith("conv_"):
        warnings.warn(
            f"`{key}` does not use the OpenAI Responses `conv_` prefix; continuing with the supplied value.",
            UserWarning,
            stacklevel=3,
        )
    return value, True


def responses_to_run(body: Mapping[str, Any]) -> AgentRunArgs:
    """Convert a Responses request body into Agent Framework run values.

    Args:
        body: OpenAI Responses-shaped request body.

    Returns:
        Arguments corresponding to ``Agent.run``.

    Raises:
        ValueError: If the request body has invalid ``input`` or continuation fields.
    """
    mark_feature_used(FeatureIndex.HOSTING_RESPONSES)
    _responses_session_id(body, warn=False)
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
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Convert an Agent Framework response into a Responses payload.

    Args:
        result: Agent response returned by a run.

    Keyword Args:
        response_id: Id for the response being created.
        conversation_id: Optional conversation id to render in the Responses
            conversation field.

    Returns:
        Responses-compatible JSON payload.
    """
    mark_feature_used(FeatureIndex.HOSTING_RESPONSES)
    status = _status_from_result(result)
    output_items = _result_to_output_items(result, status=status)
    response_kwargs: dict[str, Any] = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": status,
        "model": _model_from_result(result),
        "output": output_items,
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }
    if (metadata := _metadata_from_result(result)) is not None:
        response_kwargs["metadata"] = metadata
    if (usage := _usage_from_result(result)) is not None:
        response_kwargs["usage"] = usage
    if (error := _response_field_from_result(result, "error")) is not None:
        response_kwargs["error"] = error
    if (incomplete_details := _incomplete_details_from_result(result, status=status)) is not None:
        response_kwargs["incomplete_details"] = incomplete_details
    if conversation_id is not None:
        response_kwargs["conversation"] = {"id": conversation_id}
    return _response_payload(OpenAIResponse(**response_kwargs))


def _status_from_result(result: AgentResponse[Any]) -> str:
    transport_status = _response_field_from_result(result, "status")
    if transport_status is not None:
        if not isinstance(transport_status, str) or transport_status not in _RESPONSES_STATUSES:
            raise ValueError(f"AgentResponse status is not a valid Responses status: {transport_status!r}")
        return transport_status

    finish_reason = getattr(result.finish_reason, "value", result.finish_reason)
    if finish_reason in ("length", "content_filter"):
        return "incomplete"
    if result.continuation_token is not None:
        return "in_progress"
    return "completed"


def _metadata_from_result(result: AgentResponse[Any]) -> dict[str, str] | None:
    metadata = _response_field_from_result(result, "metadata", allow_additional_properties=True)
    if metadata is None:
        return None
    if not isinstance(metadata, Mapping):
        raise ValueError("AgentResponse metadata must be an object with string keys and values")
    metadata_dict = dict(cast("Mapping[Any, Any]", metadata))
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in metadata_dict.items()):
        raise ValueError("AgentResponse metadata must be an object with string keys and values")
    return cast("dict[str, str]", metadata_dict)


def _usage_from_result(result: AgentResponse[Any]) -> Any | None:
    if (raw_usage := _raw_response_usage_from_result(result)) is not None:
        return raw_usage

    usage_details = result.usage_details
    if not usage_details:
        return None

    input_tokens = _usage_count(usage_details, "input_token_count")
    output_tokens = _usage_count(usage_details, "output_token_count")
    total_tokens = _usage_count(usage_details, "total_token_count")
    cached_tokens = _usage_count(usage_details, "cache_read_input_token_count")
    cache_write_tokens = _usage_count(usage_details, "cache_creation_input_token_count")
    reasoning_tokens = _usage_count(usage_details, "reasoning_output_token_count")
    if input_tokens is None or output_tokens is None:
        return None

    expected_total = input_tokens + output_tokens
    cache_details = [count for count in (cached_tokens, cache_write_tokens) if count is not None]
    if sum(cache_details) > input_tokens:
        return None
    if reasoning_tokens is not None and reasoning_tokens > output_tokens:
        return None
    if total_tokens is not None and total_tokens != expected_total:
        return None
    if total_tokens is None:
        total_tokens = expected_total

    input_tokens_details: dict[str, int] = {}
    if cached_tokens is not None:
        input_tokens_details["cached_tokens"] = cached_tokens
    if cache_write_tokens is not None:
        input_tokens_details["cache_write_tokens"] = cache_write_tokens
    output_tokens_details: dict[str, int] = {}
    if reasoning_tokens is not None:
        output_tokens_details["reasoning_tokens"] = reasoning_tokens
    return _validated_response_usage({
        "input_tokens": input_tokens,
        "input_tokens_details": input_tokens_details,
        "output_tokens": output_tokens,
        "output_tokens_details": output_tokens_details,
        "total_tokens": total_tokens,
    })


def _raw_response_usage_from_result(result: AgentResponse[Any]) -> Any | None:
    for source in _raw_response_sources(result.raw_representation):
        if isinstance(source, Mapping):
            source_map = cast("Mapping[str, Any]", source)
            response_object = source_map.get("object")
            usage = source_map.get("usage")
        else:
            response_object = getattr(source, "object", None)
            usage = getattr(source, "usage", None)
        if response_object == "response" and usage is not None:
            return _validated_response_usage(usage)
    return None


def _validated_response_usage(value: Any) -> Any | None:
    try:
        _RESPONSE_USAGE_ADAPTER.validate_python(value)
    except ValidationError:
        return None
    return value


def _usage_count(usage_details: Mapping[str, Any], key: str) -> int | None:
    value = usage_details.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"AgentResponse usage_details `{key}` must be a non-negative integer")
    return value


def _incomplete_details_from_result(result: AgentResponse[Any], *, status: str) -> Any | None:
    incomplete_details = _response_field_from_result(result, "incomplete_details", allow_additional_properties=True)
    if incomplete_details is not None:
        return incomplete_details
    if status != "incomplete":
        return None

    finish_reason = getattr(result.finish_reason, "value", result.finish_reason)
    if finish_reason == "length":
        return {"reason": "max_output_tokens"}
    if finish_reason == "content_filter":
        return {"reason": "content_filter"}
    return None


def _response_field_from_result(
    result: AgentResponse[Any],
    key: str,
    *,
    allow_additional_properties: bool = False,
) -> Any | None:
    for source in _raw_response_sources(result.raw_representation):
        if isinstance(source, Mapping):
            value = cast("Mapping[str, Any]", source).get(key)
        else:
            value = getattr(source, key, None)
        if value is not None:
            return value
    if allow_additional_properties and key in result.additional_properties:
        return result.additional_properties[key]
    return None


def _raw_response_sources(raw: Any) -> Iterator[Any]:
    """Traverse raw response wrappers, preferring the latest streaming update."""
    stack = [raw]
    seen: set[int] = set()
    while stack:
        source = stack.pop()
        if source is None or id(source) in seen:
            continue
        seen.add(id(source))

        if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
            stack.extend(cast("Sequence[Any]", source))
            continue

        yield source
        if isinstance(source, Mapping):
            source_map = cast("Mapping[str, Any]", source)
            nested_raw = source_map.get("raw_representation")
            response = source_map.get("response")
        else:
            nested_raw = getattr(source, "raw_representation", None)
            response = getattr(source, "response", None)
        if nested_raw is not None:
            stack.append(nested_raw)
        if response is not None:
            stack.append(response)


def _model_from_update(update: AgentResponseUpdate) -> str | None:
    """Best-effort model id from one streamed update's raw representation.

    ``AgentResponse.from_updates`` does not carry a chunk's raw representation
    forward onto the finalized response (see ``_finalize_response`` in core),
    so ``_model_from_result`` can never find a model for a streamed result.
    Each ``AgentResponseUpdate`` still has its own raw chat chunk, which
    usually reports the model, so the streaming SSE helper captures it here
    instead.
    """
    raw = update.raw_representation
    model = getattr(raw, "model", None)
    return model if isinstance(model, str) and model else None


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

    for message in messages:
        if not isinstance(message, Message):
            output_items.extend(_output_to_output_items(message, status=status))
            continue
        message_output_items = _contents_to_output_items(message.contents, status=status)
        if message.role != "assistant" and any(_raw_type(item) == "message" for item in message_output_items):
            raise ValueError(f"Responses output messages require the `assistant` role; received {message.role!r}")
        output_items.extend(message_output_items)

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
                raise ValueError(
                    f"Responses output has no standard representation for standalone {content.type!r} content"
                )
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
    if _is_refusal_text_content(content):
        return ResponseOutputRefusal(type="refusal", refusal=content.text or "")
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


async def responses_from_streaming_run(
    stream: ResponseStream[AgentResponseUpdate, AgentResponse[Any]],
    *,
    response_id: str,
    conversation_id: str | None = None,
) -> AsyncIterator[str]:
    """Convert an Agent Framework response stream into Responses SSE events.

    Args:
        stream: Agent Framework response stream returned by ``agent.run(...,
            stream=True)``.

    Keyword Args:
        response_id: Id for the response being created.
        conversation_id: Optional conversation id to render in Responses events.

    Yields:
        Server-Sent Event strings.
    """
    created_response: dict[str, Any] = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "in_progress",
        "model": "agent",
        "output": [],
    }
    if conversation_id is not None:
        created_response["conversation"] = {"id": conversation_id}

    sequence_number = 0
    model: str | None = None
    updates: list[AgentResponseUpdate] = []
    pending_projection_updates: list[AgentResponseUpdate] = []
    committed_output_count = 0
    projection_message_id: str | None = None
    projection_message_role: str | None = None
    seen_raw_projection_keys: set[tuple[str, str]] = set()
    seen_code_interpreter_projection_keys: set[tuple[str, str]] = set()
    output_index = -1
    streamed_message_ids: list[str] = []
    message_id: str | None = None
    message_parts: list[dict[str, Any]] = []
    content_index = -1
    content_type: Literal["output_text", "refusal"] | None = None
    content_text: str = ""

    def event(event_type: str, **payload: Any) -> str:
        nonlocal sequence_number
        result = _sse_event(
            event_type,
            {
                "type": event_type,
                **payload,
                "sequence_number": sequence_number,
            },
        )
        sequence_number += 1
        return result

    def part_value(part_type: Literal["output_text", "refusal"], text: str) -> dict[str, Any]:
        if part_type == "refusal":
            return {"type": "refusal", "refusal": text}
        return {"type": "output_text", "text": text, "annotations": []}

    def close_content_part() -> list[str]:
        nonlocal content_type, content_text
        if message_id is None or content_type is None:
            return []
        part = part_value(content_type, content_text)
        message_parts.append(part)
        if content_type == "refusal":
            done = event(
                "response.refusal.done",
                item_id=message_id,
                output_index=output_index,
                content_index=content_index,
                refusal=content_text,
            )
        else:
            done = event(
                "response.output_text.done",
                item_id=message_id,
                output_index=output_index,
                content_index=content_index,
                text=content_text,
                logprobs=[],
            )
        part_done = event(
            "response.content_part.done",
            item_id=message_id,
            output_index=output_index,
            content_index=content_index,
            part=part,
        )
        content_type = None
        content_text = ""
        return [done, part_done]

    def close_message(status: str) -> list[str]:
        nonlocal message_id, message_parts, content_index
        if message_id is None:
            return []
        events = close_content_part()
        events.append(
            event(
                "response.output_item.done",
                output_index=output_index,
                item={
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "status": _message_status(status),
                    "content": list(message_parts),
                },
            )
        )
        message_id = None
        message_parts = []
        content_index = -1
        return events

    def projected_message_output_index(current_update: AgentResponseUpdate) -> int:
        projected_response = AgentResponse.from_updates([*pending_projection_updates, current_update])
        projected_items = _result_to_output_items(projected_response, status="in_progress")
        for index in range(len(projected_items) - 1, -1, -1):
            if _raw_type(projected_items[index]) == "message":
                return committed_output_count + index
        raise RuntimeError("Text content did not produce a Responses message output item")

    def open_message(requested_message_id: str | None, projected_output_index: int) -> str:
        nonlocal message_id, output_index
        output_index = projected_output_index
        message_id = requested_message_id or f"msg_{uuid.uuid4().hex}"
        if message_id in streamed_message_ids:
            message_id = f"msg_{uuid.uuid4().hex}"
        streamed_message_ids.append(message_id)
        return event(
            "response.output_item.added",
            output_index=output_index,
            item={
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "status": "in_progress",
                "content": [],
            },
        )

    def open_content_part(part_type: Literal["output_text", "refusal"]) -> str:
        nonlocal content_index, content_type, content_text
        if message_id is None:
            raise RuntimeError("Cannot open response content without a message")
        content_index += 1
        content_type = part_type
        content_text = ""
        return event(
            "response.content_part.added",
            item_id=message_id,
            output_index=output_index,
            content_index=content_index,
            part=part_value(part_type, ""),
        )

    def content_part_matches(part_type: Literal["output_text", "refusal"]) -> bool:
        return content_type == part_type

    def apply_streamed_message_ids(response: dict[str, Any]) -> None:
        message_ids = iter(streamed_message_ids)
        for output_item in response.get("output", []):
            if not isinstance(output_item, MutableMapping):
                continue
            output_mapping = cast("MutableMapping[str, Any]", output_item)
            if output_mapping.get("type") == "message":
                try:
                    output_mapping["id"] = next(message_ids)
                except StopIteration:
                    return

    yield event("response.created", response=created_response)

    try:
        mark_feature_used(FeatureIndex.HOSTING_RESPONSES)
        async for update in stream:
            updates.append(update)
            if model is None:
                model = _model_from_update(update)
            update_role = update.role or projection_message_role
            projection_message_changed = (
                projection_message_role is not None
                and update_role is not None
                and update_role != projection_message_role
            ) or (
                projection_message_id is not None
                and update.message_id is not None
                and update.message_id != projection_message_id
            )
            if projection_message_changed:
                if message_id is not None:
                    for stream_event in close_message("completed"):
                        yield stream_event
                    committed_output_count = output_index + 1
                seen_raw_projection_keys.clear()
                seen_code_interpreter_projection_keys.clear()
            if update_role is not None:
                projection_message_role = update_role
            if update.message_id is not None:
                projection_message_id = update.message_id
            for content in update.contents:
                projected_update = copy(update)
                projected_update.contents = [content]
                if content.type == "text":
                    text = content.text
                    if not isinstance(text, str):
                        continue
                    is_active_annotation_carrier = (
                        not text
                        and bool(content.annotations)
                        and message_id is not None
                        and (update.message_id is None or update.message_id == message_id)
                    )
                    if is_active_annotation_carrier:
                        continue
                else:
                    if code_key := _code_interpreter_projection_key(content):
                        if code_key in seen_code_interpreter_projection_keys:
                            if message_id is not None:
                                for stream_event in close_content_part():
                                    yield stream_event
                            continue
                        seen_code_interpreter_projection_keys.add(code_key)
                    raw_item = _raw_response_output_item(content.raw_representation)
                    if raw_item is not None:
                        raw_key = _response_output_item_key(raw_item)
                        if raw_key in seen_raw_projection_keys:
                            continue
                        seen_raw_projection_keys.add(raw_key)
                    if content.type == "usage":
                        continue
                    if content.type == "error" and message_id is not None:
                        continue
                    if message_id is not None:
                        for stream_event in close_message("completed"):
                            yield stream_event
                        committed_output_count = output_index + 1
                    pending_projection_updates.append(projected_update)
                    continue
                requested_message_id = update.message_id
                message_changed = (
                    message_id is not None and requested_message_id is not None and requested_message_id != message_id
                )
                if message_changed:
                    for stream_event in close_message("completed"):
                        yield stream_event
                    committed_output_count = output_index + 1
                if message_id is None:
                    projected_output_index = projected_message_output_index(projected_update)
                    yield open_message(requested_message_id, projected_output_index)
                    pending_projection_updates.clear()
                requested_content_type: Literal["output_text", "refusal"] = (
                    "refusal" if _is_refusal_text_content(content) else "output_text"
                )
                if not content_part_matches(requested_content_type):
                    for stream_event in close_content_part():
                        yield stream_event
                    yield open_content_part(requested_content_type)
                content_text += text
                if not text:
                    continue
                delta_type = (
                    "response.refusal.delta" if requested_content_type == "refusal" else "response.output_text.delta"
                )
                delta_payload: dict[str, Any] = {
                    "item_id": message_id,
                    "output_index": output_index,
                    "content_index": content_index,
                    "delta": text,
                }
                if requested_content_type == "output_text":
                    delta_payload["logprobs"] = []
                yield event(delta_type, **delta_payload)

        final = await stream.get_final_response()
        payload = responses_from_run(final, response_id=response_id, conversation_id=conversation_id)
        apply_streamed_message_ids(payload)
        if model is not None:
            # The finalized `AgentResponse` never carries a raw representation
            # (see `_model_from_update`), so prefer the model observed on the
            # stream's own chunks over `responses_from_run`'s "agent" fallback.
            payload["model"] = model
        status = payload.get("status")
        if not isinstance(status, str) or status not in _STREAMING_TERMINAL_STATUSES:
            raise ValueError(
                f"Response stream finalized with unsupported status {status!r}; "
                "expected `completed`, `incomplete`, or `failed`"
            )
        for stream_event in close_message(status):
            yield stream_event
        terminal_event_type = f"response.{status}"
        yield event(terminal_event_type, response=payload)
    except Exception as exc:
        for stream_event in close_message("incomplete"):
            yield stream_event
        partial_contents = [
            content for update in updates for content in update.contents if content.type == "text" and content.text
        ]
        response_kwargs: dict[str, Any] = {
            "id": response_id,
            "object": "response",
            "created_at": int(time.time()),
            "status": "failed",
            "model": model or "agent",
            "output": _contents_to_output_items(partial_contents, status="failed"),
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "metadata": {},
            "error": {
                "code": "server_error",
                "message": str(exc),
            },
        }
        if conversation_id is not None:
            response_kwargs["conversation"] = {"id": conversation_id}
        failed_response = _response_payload(OpenAIResponse(**response_kwargs))
        apply_streamed_message_ids(failed_response)
        yield event(
            "response.failed",
            response=failed_response,
        )


__all__ = [
    "create_response_id",
    "messages_from_responses_input",
    "responses_from_run",
    "responses_from_streaming_run",
    "responses_session_id",
    "responses_to_run",
]
