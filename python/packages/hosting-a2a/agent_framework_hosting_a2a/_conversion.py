# Copyright (c) Microsoft. All rights reserved.

"""Conversion between native A2A values and Agent Framework run values."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Collection, Mapping, Sequence
from typing import Any, cast

from a2a.types import Message as A2AMessage
from a2a.types import Part
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    ChatOptions,
    Content,
    Message,
    Workflow,
    WorkflowRunResult,
)
from agent_framework_hosting import AgentRunArgs
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Value
from pydantic import TypeAdapter
from pydantic.errors import PydanticSchemaGenerationError

logger = logging.getLogger("agent_framework.hosting.a2a")

_BINARY_MODE = "application/octet-stream"
_JSON_MODE = "application/json"
_TEXT_MODE = "text"
_MODE_ORDER = (_TEXT_MODE, _BINARY_MODE, _JSON_MODE)
_JSON_SCHEMA_TYPES = {"array", "boolean", "integer", "null", "number", "object"}


def _normalized_modes(allowed_modes: Collection[str]) -> set[str]:
    normalized_modes: set[str] = set()
    for mode in allowed_modes:
        if not isinstance(mode, str) or not mode.strip():
            raise ValueError("A2A modes must be non-empty strings.")
        normalized_modes.add(mode.lower())
    return normalized_modes


def _mode_allowed(mode: str, normalized_modes: Collection[str]) -> bool:
    normalized_mode = mode.lower()
    if normalized_mode in normalized_modes:
        return True
    return any(
        allowed_mode.endswith("/*") and normalized_mode.startswith(allowed_mode[:-1])
        for allowed_mode in normalized_modes
    )


def _part_mode(part: Part) -> str | None:
    match part.WhichOneof("content"):
        case "text":
            return _TEXT_MODE
        case "data":
            return _JSON_MODE
        case "raw":
            return part.media_type or _BINARY_MODE
        case "url":
            return part.media_type or None
        case _:
            return None


def _validate_part_modes(parts: Sequence[Part], allowed_modes: Collection[str], direction: str) -> None:
    normalized_modes = _normalized_modes(allowed_modes)
    for part in parts:
        mode = _part_mode(part)
        if mode is None:
            raise ValueError(f"Cannot determine the A2A mode for a {direction} part.")
        if _mode_allowed(mode, normalized_modes):
            continue
        raise ValueError(
            f"A2A {direction} part mode '{mode}' is not included in the advertised modes: {sorted(allowed_modes)}."
        )


def _part_from_text(
    text: str,
    metadata: Mapping[str, Any],
    output_modes: Collection[str] | None,
) -> Part:
    if output_modes is None:
        return Part(text=text, metadata=metadata)

    normalized_modes = _normalized_modes(output_modes)
    if _mode_allowed(_TEXT_MODE, normalized_modes):
        return Part(text=text, metadata=metadata)
    if _mode_allowed(_JSON_MODE, normalized_modes):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Agent Framework text output is not valid JSON for A2A application/json mode.") from exc
        value = Value()
        ParseDict(data, value)
        return Part(data=value, metadata=metadata)
    raise ValueError(
        f"Agent Framework text output cannot be converted to the advertised A2A modes: {sorted(output_modes)}."
    )


def _modes_for_schema(schema: Mapping[str, Any]) -> list[str]:
    modes: set[str] = set()
    variants = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(variants, list):
        for variant in cast("list[object]", variants):
            if isinstance(variant, dict):
                modes.update(_modes_for_schema(cast("dict[str, Any]", variant)))

    schema_types = schema.get("type")
    if isinstance(schema_types, str):
        schema_types_list: list[object] = [schema_types]
    elif isinstance(schema_types, list):
        schema_types_list = cast("list[object]", schema_types)
    else:
        schema_types_list = []
    for schema_type in schema_types_list:
        if isinstance(schema_type, str):
            if schema_type == "string":
                modes.add(_BINARY_MODE if schema.get("format") == "binary" else _TEXT_MODE)
            elif schema_type in _JSON_SCHEMA_TYPES:
                modes.add(_JSON_MODE)

    return [mode for mode in _MODE_ORDER if mode in modes]


def _workflow_input_type(workflow: Workflow) -> Any:
    input_types = workflow.input_types
    if len(input_types) != 1:
        raise ValueError(
            f"A2A workflow helpers require exactly one start-executor input type; found {len(input_types)}."
        )
    return input_types[0]


def _workflow_type_adapter(value_type: Any) -> TypeAdapter[Any]:
    try:
        return TypeAdapter(value_type)
    except PydanticSchemaGenerationError as exc:
        raise ValueError(f"Cannot convert A2A values for workflow type {value_type!r}.") from exc


def _workflow_input_adapter(workflow: Workflow) -> TypeAdapter[Any]:
    return _workflow_type_adapter(_workflow_input_type(workflow))


def _workflow_type_modes(value_type: Any) -> list[str]:  # pyright: ignore[reportUnusedFunction]
    try:
        schema = _workflow_type_adapter(value_type).json_schema()
    except ValueError as exc:
        raise ValueError(f"Cannot infer an A2A mode for workflow type {value_type!r}.") from exc
    modes = _modes_for_schema(schema)
    if not modes:
        raise ValueError(f"Cannot infer an A2A mode for workflow type {value_type!r}.")
    return modes


def a2a_to_run(
    message: A2AMessage,
    *,
    stream: bool = False,
    input_modes: Collection[str] | None = None,
) -> AgentRunArgs:
    """Convert an A2A message into Agent Framework run arguments.

    A2A text, URL, raw-byte, and structured-data parts become Agent Framework
    content. The helper does not create sessions, inspect task stores, or
    interact with an A2A request handler.

    Args:
        message: Native A2A message to convert.

    Keyword Args:
        stream: Whether the caller intends to run the agent in streaming mode.
        input_modes: Advertised A2A input modes to validate against. ``None``
            disables mode validation.

    Returns:
        Arguments corresponding to ``Agent.run(...)``.

    Raises:
        ValueError: If the message has no supported content parts or contains
            a part outside ``input_modes``.
    """
    if input_modes is not None:
        _validate_part_modes(message.parts, input_modes, "input")

    contents: list[Content] = []
    for part in message.parts:
        metadata = MessageToDict(part.metadata) if part.metadata else None
        match part.WhichOneof("content"):
            case "text":
                contents.append(
                    Content.from_text(
                        text=part.text,
                        additional_properties=metadata,
                        raw_representation=part,
                    )
                )
            case "url":
                contents.append(
                    Content.from_uri(
                        uri=part.url,
                        media_type=part.media_type or None,
                        additional_properties=metadata,
                        raw_representation=part,
                    )
                )
            case "raw":
                contents.append(
                    Content.from_data(
                        data=part.raw,
                        media_type=part.media_type or "application/octet-stream",
                        additional_properties=metadata,
                        raw_representation=part,
                    )
                )
            case "data":
                contents.append(
                    Content.from_text(
                        text=json.dumps(MessageToDict(part.data), separators=(",", ":"), sort_keys=True),
                        additional_properties=metadata,
                        raw_representation=part,
                    )
                )
            case unsupported:
                logger.warning("A2A message part type %s is not supported and was omitted.", unsupported)

    if not contents:
        raise ValueError("A2A message has no supported text, URL, raw, or data parts to convert to a run.")

    return AgentRunArgs(
        messages=[
            Message(
                "user",
                contents,
                message_id=message.message_id or None,
                additional_properties={"a2a_metadata": MessageToDict(message.metadata)} if message.metadata else None,
                raw_representation=message,
            )
        ],
        options=cast("ChatOptions[Any]", {}),
        stream=stream,
    )


def a2a_from_run(
    result: AgentResponse[Any] | Message | AgentResponseUpdate,
    *,
    output_modes: Collection[str] | None = None,
) -> list[Part]:
    """Convert Agent Framework output into native A2A parts.

    ``AgentResponse`` values are flattened in message order. User-role
    messages are omitted. Text, external URI, and inline data content become
    the corresponding native A2A part types. Content-level metadata is
    preserved on each part. The caller remains responsible for grouping parts
    into A2A messages or artifacts, including message boundaries and metadata,
    and publishing them through ``TaskUpdater`` or an event queue.

    Args:
        result: A completed response, response message, or streaming update.

    Keyword Args:
        output_modes: Advertised A2A output modes to validate against. ``None``
            disables mode validation.

    Returns:
        Native A2A parts ready for an A2A SDK message or artifact.

    Raises:
        ValueError: If Agent Framework data content contains an invalid data URI
            or produces a part outside ``output_modes``.
    """
    items: Sequence[Message | AgentResponseUpdate] = result.messages if isinstance(result, AgentResponse) else [result]

    parts: list[Part] = []
    for item in items:
        if item.role == "user":
            continue
        for content in item.contents:
            metadata = content.additional_properties or {}
            match content.type:
                case "text" if content.text is not None:
                    parts.append(_part_from_text(content.text, metadata, output_modes))
                case "uri" if content.uri is not None:
                    parts.append(
                        Part(
                            url=content.uri,
                            media_type=content.media_type or "",
                            metadata=metadata,
                        )
                    )
                case "data" if content.uri is not None:
                    prefix, separator, encoded = content.uri.partition(",")
                    if not separator or not prefix.startswith("data:") or ";base64" not in prefix:
                        raise ValueError("Agent Framework data content must contain a base64 data URI.")
                    try:
                        raw = base64.b64decode(encoded, validate=True)
                    except ValueError as exc:
                        raise ValueError("Agent Framework data content contains invalid base64 data.") from exc
                    parts.append(
                        Part(
                            raw=raw,
                            media_type=content.media_type or "",
                            metadata=metadata,
                        )
                    )
                case _:
                    logger.warning(
                        "Agent Framework content type %s is not supported by A2A and was omitted.",
                        content.type,
                    )
    if output_modes is not None:
        _validate_part_modes(parts, output_modes, "output")
    return parts


def a2a_to_workflow_run(
    message: A2AMessage,
    workflow: Workflow,
    *,
    input_modes: Collection[str] | None = None,
) -> Any:
    """Convert one native A2A message part into validated workflow input.

    The workflow must declare exactly one start-executor input type. Text,
    raw-byte, and structured-data parts map to string, binary, and JSON
    workflow contracts respectively. Executor, task, session, and continuation
    behavior remain application-owned.

    Args:
        message: Native A2A message containing the workflow input.
        workflow: Workflow whose start-executor input contract should be used.

    Keyword Args:
        input_modes: Advertised A2A input modes to validate against. ``None``
            disables card-mode validation; workflow type validation still applies.

    Returns:
        A value validated for ``Workflow.run(...)``.

    Raises:
        ValueError: If the workflow input type is unsupported, the message
            does not contain exactly one compatible part, or a part is outside
            ``input_modes``.
    """
    if input_modes is not None:
        _validate_part_modes(message.parts, input_modes, "input")

    adapter = _workflow_input_adapter(workflow)
    modes = _modes_for_schema(adapter.json_schema())
    if not modes:
        raise ValueError(f"Cannot convert A2A input for workflow type {workflow.input_types[0]!r}.")

    candidates: list[tuple[str, Part]] = []
    for part in message.parts:
        content_type = part.WhichOneof("content")
        if content_type == "text" and _TEXT_MODE in modes:
            candidates.append((_TEXT_MODE, part))
        elif content_type == "raw" and _BINARY_MODE in modes:
            candidates.append((_BINARY_MODE, part))
        elif content_type == "data" and _JSON_MODE in modes:
            candidates.append((_JSON_MODE, part))

    if len(candidates) != 1:
        expected = ", ".join(modes)
        raise ValueError(
            f"A2A workflow input must contain exactly one compatible part for modes [{expected}]; "
            f"found {len(candidates)}."
        )

    mode, part = candidates[0]
    if mode == _TEXT_MODE:
        value: Any = part.text
    elif mode == _BINARY_MODE:
        value = part.raw
    else:
        value = MessageToDict(part.data)
    return adapter.validate_python(value)


def a2a_from_workflow_run(
    result: WorkflowRunResult,
    *,
    output_modes: Collection[str] | None = None,
) -> list[Part]:
    """Convert completed workflow outputs into native A2A parts.

    Args:
        result: Completed non-streaming workflow result.

    Keyword Args:
        output_modes: Advertised A2A output modes to validate against. ``None``
            disables mode validation.

    Returns:
        Native A2A parts for the workflow's public outputs.

    Raises:
        ValueError: If the workflow requires external input or produces a part
            outside ``output_modes``.
    """
    if result.get_request_info_events():
        raise ValueError(
            "The workflow requires external input. A2A workflow conversion does not manage "
            "human-in-the-loop continuation; handle it in the application contract."
        )

    parts: list[Part] = []
    for output in result.get_outputs():
        if isinstance(output, (AgentResponse, Message, AgentResponseUpdate)):
            parts.extend(
                a2a_from_run(
                    cast("AgentResponse[Any] | Message | AgentResponseUpdate", output),
                    output_modes=output_modes,
                )
            )
        elif isinstance(output, str):
            parts.append(_part_from_text(output, {}, output_modes))
        elif isinstance(output, bytes):
            parts.append(Part(raw=output, media_type=_BINARY_MODE))
        else:
            data = TypeAdapter(object).dump_python(output, mode="json", serialize_as_any=True)
            normalized_modes = _normalized_modes(output_modes) if output_modes is not None else None
            if (
                normalized_modes is not None
                and _mode_allowed(_TEXT_MODE, normalized_modes)
                and not _mode_allowed(_JSON_MODE, normalized_modes)
            ):
                parts.append(Part(text=json.dumps(data, separators=(",", ":"), sort_keys=True)))
            else:
                value = Value()
                ParseDict(data, value)
                parts.append(Part(data=value))
    if output_modes is not None:
        _validate_part_modes(parts, output_modes, "output")
    return parts
