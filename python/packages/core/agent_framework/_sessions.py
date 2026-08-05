# Copyright (c) Microsoft. All rights reserved.

"""Unified context management types for the agent framework.

This module provides the core types for the context provider pipeline:
- SessionContext: Per-invocation state passed through providers
- ContextProvider: Base class for context providers
- HistoryProvider: Base class for history storage providers
- AgentSession: Lightweight session state container
- SessionStore: In-memory session snapshot storage
- FileSessionStore: msgspec JSON file-backed session snapshot storage
- InMemoryHistoryProvider: Built-in in-memory history provider
- FileHistoryProvider: Built-in JSON Lines file history provider
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import math
import os
import threading
import uuid
import warnings
import weakref
from abc import abstractmethod
from base64 import urlsafe_b64encode
from collections import deque
from collections.abc import AsyncIterable, Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypeAlias, TypeGuard, TypeVar, cast

import msgspec

from ._feature_stage import ExperimentalFeature, experimental
from ._middleware import ChatContext, ChatMiddleware
from ._telemetry import FeatureIndex, mark_feature_used
from ._types import (
    AgentResponse,
    AgentRunInputs,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    ResponseStream,
    _build_agent_response_from_chat_response,  # pyright: ignore[reportPrivateUsage]
    normalize_messages,
)
from .exceptions import ChatClientInvalidRequestException, ChatClientInvalidResponseException

if TYPE_CHECKING:
    from ._agents import SupportsAgentRun
    from ._middleware import MiddlewareTypes


logger = logging.getLogger("agent_framework")

MESSAGE_INJECTION_PENDING_MESSAGES_STATE_KEY: str = "message_injection.pending_messages"
_MESSAGE_INJECTION_LOCK = threading.Lock()

JsonDumps: TypeAlias = Callable[[Any], str | bytes]
JsonLoads: TypeAlias = Callable[[str | bytes], Any]
ServiceSessionId: TypeAlias = Mapping[str, Any]
StateT = TypeVar("StateT")
StateEncoder: TypeAlias = Callable[[Any], Mapping[str, Any]]
StateDecoder: TypeAlias = Callable[[Mapping[str, Any]], Any]
_STATE_SCALAR_TYPES = (str, int, float, bool, type(None))
_WINDOWS_RESERVED_FILE_STEMS: frozenset[str] = frozenset({
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
    "COM¹",
    "COM²",
    "COM³",
    "LPT¹",
    "LPT²",
    "LPT³",
})


_DEFAULT_JSON_ENCODER = msgspec.json.Encoder()
_DEFAULT_JSON_DECODER = msgspec.json.Decoder()
_DEFAULT_MSGPACK_ENCODER = msgspec.msgpack.Encoder()
_DEFAULT_MSGPACK_DECODER = msgspec.msgpack.Decoder()
_JSON_FILE_EXTENSION = ".json"
_JSON_LINES_FILE_EXTENSION = ".jsonl"
_MSGPACK_FILE_EXTENSION = ".msgpack"
_SESSION_SNAPSHOT_VERSION = "1.0"
_MAX_ENCODED_SESSION_FILE_STEM_LENGTH = 180


def _default_json_dumps(value: Any) -> bytes:
    if _contains_non_finite_float(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _DEFAULT_JSON_ENCODER.encode(value)


def _default_json_loads(value: str | bytes) -> Any:
    try:
        return _DEFAULT_JSON_DECODER.decode(value)
    except msgspec.DecodeError:
        return json.loads(value)


def _contains_non_finite_float(value: Any) -> bool:
    """Return whether legacy JSON encoding is needed for NaN or infinity.

    msgspec normalizes non-finite floats to ``null``, while the previous
    FileHistoryProvider JSON encoder emitted Python's ``NaN`` and ``Infinity``
    tokens. Detecting them keeps existing history files byte-compatible.
    """
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_non_finite_float(item) for item in cast(Mapping[Any, Any], value).values())
    if isinstance(value, (list, tuple)):
        return any(_contains_non_finite_float(item) for item in cast(Sequence[Any], value))
    return False


def _is_literal_session_file_stem_safe(session_id: str) -> bool:
    """Return whether an opaque session ID is a portable filename stem.

    FileSessionStore and FileHistoryProvider accept opaque IDs, including IDs
    with separators and platform-reserved names such as ``CON``. Unsafe values
    are encoded by :func:`_session_file_stem` rather than rejected.
    """
    windows_stem = session_id.split(".", maxsplit=1)[0].upper()
    if (
        not session_id
        or session_id.startswith(".")
        or session_id.endswith((" ", "."))
        or windows_stem in _WINDOWS_RESERVED_FILE_STEMS
    ):
        return False
    if any(ord(character) < 32 for character in session_id):
        return False
    return all(character.isascii() and (character.isalnum() or character in "._-") for character in session_id)


def _session_file_stem(session_id: str, *, encoded_prefix: str) -> str:
    """Return a safe filename stem for an opaque session ID."""
    if _is_literal_session_file_stem_safe(session_id):
        return session_id
    encoded_session_id = urlsafe_b64encode(session_id.encode("utf-8")).decode("ascii").rstrip("=")
    encoded_stem = f"{encoded_prefix}{encoded_session_id}"
    if len(encoded_stem) <= _MAX_ENCODED_SESSION_FILE_STEM_LENGTH:
        return encoded_stem
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return f"{encoded_prefix}sha256-{digest}"


def _deduplicate_origin_session_ids(origin_session_ids: Iterable[str]) -> list[str]:
    """Return origin session IDs in first-seen order without duplicates."""
    unique_origin_session_ids: list[str] = []
    seen_origin_session_ids: set[str] = set()
    for origin_session_id in origin_session_ids:
        if origin_session_id not in seen_origin_session_ids:
            seen_origin_session_ids.add(origin_session_id)
            unique_origin_session_ids.append(origin_session_id)
    return unique_origin_session_ids


def _is_middleware_sequence(
    middleware: MiddlewareTypes | Sequence[MiddlewareTypes],
) -> TypeGuard[Sequence[MiddlewareTypes]]:
    return isinstance(middleware, Sequence) and not isinstance(middleware, (str, bytes))


def _is_single_middleware(
    middleware: MiddlewareTypes | Sequence[MiddlewareTypes],
) -> TypeGuard[MiddlewareTypes]:
    return not _is_middleware_sequence(middleware)


@dataclass(frozen=True, slots=True)
class _StateTypeRegistration:
    cls: type[Any]
    type_id: str
    encoder: StateEncoder
    decoder: StateDecoder


_STATE_TYPE_REGISTRY: dict[str, _StateTypeRegistration] = {}
_STATE_CLASS_REGISTRY: dict[type[Any], _StateTypeRegistration] = {}


def _resolve_state_type_id(cls: type[Any], type_id: str | None) -> str:
    """Resolve the stable, process-wide ID for a registered state type."""
    if type_id is not None:
        resolved = type_id
    elif callable(identifier := getattr(cls, "_get_type_identifier", None)):
        resolved = identifier()
    elif isinstance(identifier := getattr(cls, "TYPE", None), str):
        resolved = identifier
    else:
        resolved = cls.__name__.lower()
    if not isinstance(resolved, str) or not resolved:
        raise ValueError("State type identifier must be a non-empty string.")
    return resolved


def _default_state_encoder(cls: type[Any]) -> StateEncoder:
    """Create the default encoder for one explicitly registered state type."""
    if callable(getattr(cls, "to_dict", None)):

        def encode_to_dict(value: Any) -> Mapping[str, Any]:
            payload = value.to_dict()
            if not isinstance(payload, Mapping):
                raise TypeError(f"{cls.__name__}.to_dict() must return a mapping.")
            return cast(Mapping[str, Any], payload)

        return encode_to_dict

    from pydantic import BaseModel

    if issubclass(cls, BaseModel):

        def encode_pydantic(value: Any) -> Mapping[str, Any]:
            return cast(Mapping[str, Any], value.model_dump())

        return encode_pydantic

    raise ValueError(
        f"State type {cls.__name__!r} must define to_dict()/from_dict(), be a Pydantic model, "
        "or provide encoder and decoder callbacks."
    )


def _default_state_decoder(cls: type[Any]) -> StateDecoder:
    """Create the default decoder for one explicitly registered state type."""
    if callable(getattr(cls, "from_dict", None)):

        def decode_from_dict(payload: Mapping[str, Any]) -> Any:
            return cls.from_dict(dict(payload))

        return decode_from_dict

    from pydantic import BaseModel

    if issubclass(cls, BaseModel):

        def decode_pydantic(payload: Mapping[str, Any]) -> Any:
            return cls.model_validate({key: value for key, value in payload.items() if key != "type"})

        return decode_pydantic

    raise ValueError(
        f"State type {cls.__name__!r} must define to_dict()/from_dict(), be a Pydantic model, "
        "or provide encoder and decoder callbacks."
    )


def register_state_type(
    cls: type[StateT],
    *,
    type_id: str | None = None,
    encoder: Callable[[StateT], Mapping[str, Any]] | None = None,
    decoder: Callable[[Mapping[str, Any]], StateT] | None = None,
) -> None:
    """Register a type for automatic deserialization in session state.

    Registration is explicit so persisted sessions can be restored after a
    process restart. Type identifiers share one process-wide registry and must
    therefore be globally unique; provider packages should pass a stable,
    package-qualified ``type_id``. For compatibility with existing framework
    types, the identifier otherwise falls back to ``_get_type_identifier()``,
    then ``TYPE``, and finally the lowercased class name. Conflicting
    registrations fail immediately rather than silently selecting one type.
    Classes implementing ``to_dict`` / ``from_dict`` and Pydantic models receive
    default codecs; other classes must provide both callbacks.

    Call this at module level immediately after defining the custom state class.
    Importing that module then registers the type before any persisted session
    is loaded, without requiring the related context provider to be instantiated
    first.

    Args:
        cls: The type to register.

    Keyword Args:
        type_id: Stable identifier stored in the serialized ``type`` field.
        encoder: Optional callback that converts an instance to a mapping.
        decoder: Optional callback that reconstructs an instance from a mapping.

    Raises:
        ValueError: If the registration is incomplete or conflicts with an existing type.
    """
    resolved_type_id = _resolve_state_type_id(cls, type_id)
    existing_for_class = _STATE_CLASS_REGISTRY.get(cls)
    if existing_for_class is not None:
        if existing_for_class.type_id != resolved_type_id:
            raise ValueError(
                f"State type {cls.__name__!r} is already registered as {existing_for_class.type_id!r}, "
                f"not {resolved_type_id!r}."
            )
        if encoder is not None and existing_for_class.encoder is not encoder:
            raise ValueError(f"State type {cls.__name__!r} is already registered with a different encoder.")
        if decoder is not None and existing_for_class.decoder is not decoder:
            raise ValueError(f"State type {cls.__name__!r} is already registered with a different decoder.")
        return

    existing_for_id = _STATE_TYPE_REGISTRY.get(resolved_type_id)
    if existing_for_id is not None:
        raise ValueError(
            f"State type identifier {resolved_type_id!r} is already registered for {existing_for_id.cls.__name__!r}."
        )

    if (encoder is None) != (decoder is None):
        raise ValueError("State type encoder and decoder must be provided together.")
    resolved_encoder = cast(StateEncoder, encoder) if encoder is not None else _default_state_encoder(cls)
    resolved_decoder = cast(StateDecoder, decoder) if decoder is not None else _default_state_decoder(cls)
    registration = _StateTypeRegistration(
        cls=cls,
        type_id=resolved_type_id,
        encoder=resolved_encoder,
        decoder=resolved_decoder,
    )
    _STATE_TYPE_REGISTRY[resolved_type_id] = registration
    _STATE_CLASS_REGISTRY[cls] = registration


def _warn_implicit_pydantic_registration(value_type: type[Any]) -> None:
    """Warn that an unregistered Pydantic state type uses legacy registration."""
    warnings.warn(
        f"Implicit registration of Pydantic AgentSession state type {value_type.__name__!r} is deprecated and will "
        "be removed in a future version. Call register_state_type() at module import time. Cold-start deserialization "
        "is not guaranteed without explicit registration.",
        DeprecationWarning,
        stacklevel=4,
    )


def _serialize_value(value: Any, *, path: str) -> Any:
    """Serialize one session-state value through the shared compatibility path."""
    value_type = cast(type[Any], type(value))
    registration = _STATE_CLASS_REGISTRY.get(value_type)
    if registration is not None:
        payload = registration.encoder(value)
        payload_type = payload.get("type")
        if payload_type is not None and payload_type != registration.type_id:
            raise ValueError(
                f"State encoder for {registration.cls.__name__!r} returned type {payload_type!r}; "
                f"expected {registration.type_id!r}."
            )
        serialized = {
            str(key): _serialize_value(item, path=f"{path}.{key}") for key, item in payload.items() if key != "type"
        }
        serialized["type"] = registration.type_id
        return serialized
    if callable(getattr(value, "to_dict", None)):
        payload = value.to_dict()
        if not isinstance(payload, Mapping):
            raise TypeError(f"{value_type.__name__}.to_dict() must return a mapping.")
        return {
            str(key): _serialize_value(item, path=f"{path}.{key}")
            for key, item in cast(Mapping[Any, Any], payload).items()
        }
    if value_type in _STATE_SCALAR_TYPES:
        return value
    if isinstance(value, list):
        return [_serialize_value(item, path=f"{path}[{index}]") for index, item in enumerate(cast(list[Any], value))]
    if isinstance(value, tuple):
        return [
            _serialize_value(item, path=f"{path}[{index}]") for index, item in enumerate(cast(tuple[Any, ...], value))
        ]
    if isinstance(value, Mapping):
        return {
            str(key): _serialize_value(item, path=f"{path}.{key}")
            for key, item in cast(Mapping[Any, Any], value).items()
        }

    from pydantic import BaseModel

    if isinstance(value, BaseModel):
        # Temporary compatibility fallback for unregistered Pydantic models;
        # remove this branch together with implicit auto-registration.
        _warn_implicit_pydantic_registration(value_type)
        type_id = _resolve_state_type_id(value_type, None)
        register_state_type(value_type, type_id=type_id)
        return _serialize_value(value, path=path)
    warnings.warn(
        f"AgentSession state value at {path} has unsupported type {value_type.__name__!r}; "
        "AgentSession.to_dict() is leaving it unchanged for compatibility, but durable session stores will reject it. "
        "Call register_state_type() with a restorable codec.",
        RuntimeWarning,
        stacklevel=4,
    )
    return value


def _deserialize_value(value: Any, *, path: str) -> Any:
    """Deserialize a single value, restoring registered types."""
    if isinstance(value, list):
        return [_deserialize_value(item, path=f"{path}[{index}]") for index, item in enumerate(cast(list[Any], value))]
    if isinstance(value, Mapping):
        raw_mapping = {str(key): item for key, item in cast(Mapping[Any, Any], value).items()}
        if "type" in raw_mapping:
            registration = _STATE_TYPE_REGISTRY.get(str(raw_mapping["type"]))
            if registration is not None:
                try:
                    return registration.decoder(raw_mapping)
                except Exception as exc:
                    # Registered decoders are application extension points. Any
                    # ordinary failure means this payload cannot be restored by
                    # the active registration and should enter store recovery.
                    raise ValueError(
                        f"Failed to deserialize registered state type {registration.type_id!r} at {path}."
                    ) from exc
        return {key: _deserialize_value(item, path=f"{path}.{key}") for key, item in raw_mapping.items()}
    return value


def _serialize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Deep-serialize a state dict using the established AgentSession contract."""
    return {key: _serialize_value(value, path=f"state.{key}") for key, value in state.items()}


def _validate_durable_state_value(value: Any, *, path: str) -> None:
    """Validate that serialized state can round-trip through the durable codecs."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"Session state value at {path} must be a finite float.")
    if type(value) in _STATE_SCALAR_TYPES:
        return
    if isinstance(value, list):
        for index, item in enumerate(cast(list[Any], value)):
            _validate_durable_state_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in cast(Mapping[Any, Any], value).items():
            _validate_durable_state_value(item, path=f"{path}.{key}")
        return
    raise TypeError(
        f"Session state value at {path} has unsupported serialized type {type(value).__name__!r}; "
        "call register_state_type() with a codec that returns JSON-compatible values."
    )


def _deserialize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Deep-deserialize a state dict, restoring SerializationProtocol objects."""
    return {key: _deserialize_value(value, path=f"state.{key}") for key, value in state.items()}


class _SessionStatePayload:
    """Wrapper that routes the complete dynamic state mapping through msgspec hooks."""

    __slots__ = ("value",)

    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value

    def serialize(self) -> dict[str, Any]:
        """Serialize and validate the wrapped state for durable storage."""
        serialized = _serialize_state(self.value)
        _validate_durable_state_value(serialized, path="state")
        return serialized


class _SessionSnapshot(msgspec.Struct):
    """Typed on-disk representation of one AgentSession."""

    type: Literal["session"]
    session_id: str
    service_session_id: str | dict[str, Any] | None
    state: object
    version: str = _SESSION_SNAPSHOT_VERSION


def _session_snapshot_enc_hook(value: Any) -> Any:
    """Encode the complete dynamic state payload for msgspec."""
    if isinstance(value, _SessionStatePayload):
        return value.serialize()
    raise NotImplementedError(f"Objects of type {type(value).__name__!r} are not supported.")


_SESSION_SNAPSHOT_ENCODER = msgspec.json.Encoder(enc_hook=_session_snapshot_enc_hook)
_SESSION_SNAPSHOT_DECODER = msgspec.json.Decoder(_SessionSnapshot)
_SESSION_SNAPSHOT_MSGPACK_ENCODER = msgspec.msgpack.Encoder(enc_hook=_session_snapshot_enc_hook)
_SESSION_SNAPSHOT_MSGPACK_DECODER = msgspec.msgpack.Decoder(_SessionSnapshot)


# Register known types
register_state_type(Message)


class SessionContext:
    """Per-invocation state passed through the context provider pipeline.

    Created fresh for each agent.run() call. Providers read from and write to
    the mutable fields to add context before invocation and process responses after.

    Attributes:
        session_id: The ID of the current session.
        service_session_id: Service-managed session identifier
            (if present, the service stores history).
        input_messages: The new messages being sent to the agent (set by caller).
        context_messages: Dict mapping source_id -> messages added by that provider.
            Maintains insertion order (provider execution order).
        instructions: Additional instructions added by providers.
        tools: Additional tools added by providers.
        middleware: Dict mapping source_id -> chat/function middleware added by that provider.
            Maintains insertion order (provider execution order).
        response: After invocation, contains the full AgentResponse, should not be changed.
        options: Options passed to agent.run() - read-only, for reflection only.
        metadata: Shared metadata dictionary for cross-provider communication.
    """

    def __init__(
        self,
        *,
        session_id: str | None = None,
        service_session_id: str | ServiceSessionId | None = None,
        input_messages: list[Message],
        context_messages: dict[str, list[Message]] | None = None,
        instructions: list[str] | None = None,
        tools: list[Any] | None = None,
        middleware: dict[str, list[MiddlewareTypes]] | None = None,
        options: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize the session context.

        Args:
            session_id: The ID of the current session.
            service_session_id: Service-managed session identifier.
            input_messages: The new messages being sent to the agent.
            context_messages: Pre-populated context messages by source.
            instructions: Pre-populated instructions.
            tools: Pre-populated tools.
            middleware: Pre-populated chat/function middleware by source.
            options: Options from agent.run() - read-only for providers.
            metadata: Shared metadata for cross-provider communication.
        """
        self.session_id = session_id
        self.service_session_id = service_session_id
        self.input_messages = input_messages
        self.context_messages: dict[str, list[Message]] = context_messages or {}
        self.instructions: list[str] = instructions or []
        self.tools: list[Any] = tools or []
        self.middleware: dict[str, list[MiddlewareTypes]] = {}
        if middleware:
            for source_id, provider_middleware in middleware.items():
                self.extend_middleware(source_id, provider_middleware)
        self._response: AgentResponse | None = None
        self.options: dict[str, Any] = options or {}
        self.metadata: dict[str, Any] = metadata or {}

    @property
    def response(self) -> AgentResponse | None:
        """The agent's response. Set by the framework after invocation, read-only for providers."""
        return self._response

    def extend_messages(
        self,
        source: str | object,
        messages: Sequence[Message],
        *,
        origin_session_ids: Sequence[str] | None = None,
    ) -> None:
        """Add context messages from a specific source.

        Messages are copied before attribution is added, so the caller's
        original message objects are never mutated. The copies are stored
        keyed by source_id, maintaining insertion order based on provider
        execution order. Each message gets an ``attribution`` marker in
        ``additional_properties`` for downstream filtering.

        Args:
            source: Either a plain ``source_id`` string, or an object with a
                ``source_id`` attribute (e.g. a context provider). When an
                object is passed, its class name is recorded as
                ``source_type`` in the attribution.
            messages: The messages to add.

        Keyword Args:
            origin_session_ids: Optional session IDs that originally produced
                these messages, when different from the current session. Set
                by providers that inject content stored under other sessions
                (cross-session memory). The IDs describe the contributing
                sessions for every message supplied in this call; they are not
                positionally paired with messages, and a composed message can
                have multiple origins. The values are exposed under
                ``additional_properties["_attribution"]["origin_session_ids"]``
                so downstream context observers can detect cross-session
                content for governance, audit, or behavioral-analysis
                purposes. Omit (default) when content originates in the
                current session; absence of the field means that no origin
                information was supplied.
        """
        if isinstance(source, str):
            source_id = source
            attribution: dict[str, Any] = {"source_id": source_id}
        else:
            source_id = source.source_id  # type: ignore[attr-defined]
            attribution = {"source_id": source_id, "source_type": type(source).__name__}
        if origin_session_ids:
            attribution["origin_session_ids"] = _deduplicate_origin_session_ids(origin_session_ids)

        copied: list[Message] = []
        for message in messages:
            msg_copy = copy.copy(message)
            msg_copy.additional_properties = dict(message.additional_properties)
            message_attribution = dict(attribution)
            if "origin_session_ids" in message_attribution:
                message_attribution["origin_session_ids"] = list(message_attribution["origin_session_ids"])
            existing_attribution = msg_copy.additional_properties.get("_attribution")
            if isinstance(existing_attribution, Mapping):
                merged_attribution = dict(cast(Mapping[str, Any], existing_attribution))
                for key, value in message_attribution.items():
                    if key == "origin_session_ids":
                        existing_origins = merged_attribution.get(key)
                        if isinstance(existing_origins, Sequence) and not isinstance(existing_origins, str):
                            existing_origin_values = cast(Sequence[Any], existing_origins)
                            value = _deduplicate_origin_session_ids(
                                [origin for origin in existing_origin_values if isinstance(origin, str)]
                                + cast(list[str], value)
                            )
                        merged_attribution[key] = value
                    else:
                        merged_attribution.setdefault(key, value)
                msg_copy.additional_properties["_attribution"] = merged_attribution
            else:
                msg_copy.additional_properties.setdefault("_attribution", message_attribution)
            copied.append(msg_copy)
        if source_id not in self.context_messages:
            self.context_messages[source_id] = []
        self.context_messages[source_id].extend(copied)

    def extend_instructions(self, source_id: str, instructions: str | Sequence[str]) -> None:
        """Add instructions to be prepended to the conversation.

        Args:
            source_id: The provider source_id adding these instructions.
            instructions: A single instruction string or sequence of strings.
        """
        if isinstance(instructions, str):
            instructions = [instructions]
        self.instructions.extend(instructions)

    def extend_tools(self, source_id: str, tools: Sequence[Any]) -> None:
        """Add tools to be available for this invocation.

        Tools are added with source attribution in their metadata.

        Args:
            source_id: The provider source_id adding these tools.
            tools: The tools to add.
        """
        for tool in tools:
            if hasattr(tool, "additional_properties"):
                additional_properties_obj = tool.additional_properties
                if isinstance(additional_properties_obj, dict):
                    additional_properties = cast(dict[str, Any], additional_properties_obj)
                    additional_properties["context_source"] = source_id
        self.tools.extend(tools)

    def extend_middleware(
        self,
        source_id: str,
        middleware: MiddlewareTypes | Sequence[MiddlewareTypes],
    ) -> None:
        """Add middleware to be applied for this invocation.

        Args:
            source_id: The provider source_id adding this middleware.
            middleware: A single chat/function middleware object/callable or sequence of middleware.
        """
        from ._middleware import categorize_middleware
        from .exceptions import MiddlewareException

        if _is_middleware_sequence(middleware):
            middleware_items = list(middleware)
        elif _is_single_middleware(middleware):
            middleware_items = [middleware]
        else:
            raise TypeError("middleware must be a middleware object or a sequence of middleware objects.")
        middleware_list = categorize_middleware(middleware_items)
        if middleware_list["agent"]:
            raise MiddlewareException("Context providers may only add chat or function middleware.")
        if source_id not in self.middleware:
            self.middleware[source_id] = []
        self.middleware[source_id].extend(middleware_items)

    def get_middleware(self) -> list[MiddlewareTypes]:
        """Get provider-added chat/function middleware in provider execution order."""
        result: list[MiddlewareTypes] = []
        for middleware_items in self.middleware.values():
            result.extend(middleware_items)
        return result

    def get_messages(
        self,
        *,
        sources: set[str] | None = None,
        exclude_sources: set[str] | None = None,
        include_input: bool = False,
        include_response: bool = False,
    ) -> list[Message]:
        """Get context messages, optionally filtered and including input/response.

        Returns messages in provider execution order (dict insertion order),
        with input and response appended if requested.

        Args:
            sources: If provided, only include context messages from these sources.
            exclude_sources: If provided, exclude context messages from these sources.
            include_input: If True, append input_messages after context.
            include_response: If True, append response.messages at the end.

        Returns:
            Flattened list of messages in conversation order.
        """
        result: list[Message] = []
        for source_id, messages in self.context_messages.items():
            if sources is not None and source_id not in sources:
                continue
            if exclude_sources is not None and source_id in exclude_sources:
                continue
            result.extend(messages)
        if include_input and self.input_messages:
            result.extend(self.input_messages)
        if include_response and self.response and self.response.messages:
            result.extend(self.response.messages)
        return result


class ContextProvider:
    """Base class for context providers.

    Context providers participate in the context engineering pipeline,
    adding context before model invocation and processing responses after.

    Provider-scoped ``state`` is stored inside :attr:`AgentSession.state` and
    may be persisted by a session store. Standard JSON-native Python values
    (``None``, booleans, integers, finite floats, strings, lists, tuples, and
    mappings) require no registration. If a provider stores an instance of a
    custom class or Pydantic model, the provider module must call
    :func:`register_state_type` for that class at module level, immediately
    after its definition. Importing the provider then registers the type before
    a persisted session is loaded, without requiring the application to know
    which internal state types the provider uses. Framework-owned state types
    such as :class:`Message` are registered by Agent Framework.

    Attributes:
        source_id: Unique identifier for this provider instance (required).
            Used for message/tool attribution so other providers can filter.
    """

    def __init__(self, source_id: str):
        """Initialize the provider.

        Args:
            source_id: Unique identifier for this provider instance.
        """
        self.source_id = source_id

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Called before model invocation.

        Override to add context (messages, instructions, tools) to the
        SessionContext before the model is invoked.

        Args:
            agent: The agent running this invocation.
            session: The current session.
            context: The invocation context - add messages/instructions/tools/chat/function middleware here.
            state: The provider-scoped mutable state dict for this provider.
                Full cross-provider state remains available at ``session.state``.
        """

    async def after_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Called after model invocation.

        Override to process the response (store messages, extract info, etc.).
        The context.response will be populated at this point.

        Args:
            agent: The agent that ran this invocation.
            session: The current session.
            context: The invocation context with response populated.
            state: The provider-scoped mutable state dict for this provider.
                Full cross-provider state remains available at ``session.state``.
        """


def _is_approval_placeholder_result(content: Content) -> bool:
    result = getattr(content, "result", None)
    return isinstance(result, str) and "[APPROVAL_PENDING]" in result


def _approval_controls_to_keep(messages: Sequence[Message]) -> set[int]:
    unresolved_requests_by_id: dict[str, Content] = {}
    unresolved_local_responses_by_id: dict[str, Content] = {}
    local_response_ids_by_call_id: dict[str, deque[str]] = {}

    for message in messages:
        for content in message.contents:
            if content.type == "function_approval_request":
                function_call = content.function_call
                if content.id is not None and function_call is not None and function_call.call_id is not None:
                    unresolved_requests_by_id.setdefault(content.id, content)
                continue
            if content.type == "function_approval_response":
                function_call = content.function_call
                if content.id is not None:
                    unresolved_requests_by_id.pop(content.id, None)
                if (
                    content.id is not None
                    and function_call is not None
                    and function_call.call_id is not None
                    and not function_call.additional_properties.get("server_label")
                    and content.id not in unresolved_local_responses_by_id
                ):
                    unresolved_local_responses_by_id[content.id] = content
                    local_response_ids_by_call_id.setdefault(function_call.call_id, deque()).append(content.id)
                continue
            if content.call_id is None:
                continue
            is_terminal_result = content.type == "function_result" and not _is_approval_placeholder_result(content)
            is_follow_up_request = content.user_input_request and content.type not in {
                "function_approval_request",
                "function_approval_response",
            }
            if not (is_terminal_result or is_follow_up_request):
                continue
            if response_ids := local_response_ids_by_call_id.get(content.call_id):
                unresolved_local_responses_by_id.pop(response_ids.popleft(), None)

    return {
        id(content) for content in (*unresolved_requests_by_id.values(), *unresolved_local_responses_by_id.values())
    }


def _filter_approval_control_messages(messages: Sequence[Message]) -> list[Message]:
    """Remove resolved approval controls while preserving pending occurrences."""
    controls_to_keep = _approval_controls_to_keep(messages)
    filtered_messages: list[Message] = []
    for message in messages:
        filtered_contents = [
            content
            for content in message.contents
            if content.type not in {"function_approval_request", "function_approval_response"}
            or id(content) in controls_to_keep
        ]
        if not filtered_contents:
            continue
        if len(filtered_contents) == len(message.contents):
            filtered_messages.append(message)
            continue
        filtered_message = copy.copy(message)
        filtered_message.contents = filtered_contents
        filtered_messages.append(filtered_message)
    return filtered_messages


class HistoryProvider(ContextProvider):
    """Base class for conversation history storage providers.

    A single class configurable for different use cases:
    - Primary memory storage (loads + stores messages)
    - Audit/logging storage (stores only, doesn't load)
    - Evaluation storage (stores only for later analysis)

    Subclasses only need to implement ``get_messages()`` and ``save_messages()``.
    The default ``before_run``/``after_run`` handle loading and storing based on
    configuration flags. Override them for custom behavior.

    Normal :class:`Message` history requires no custom registration because
    Agent Framework registers ``Message`` for session persistence. If a history
    provider stores any other custom class or Pydantic model in its
    provider-scoped ``state`` or elsewhere in :attr:`AgentSession.state`, the
    provider module must call :func:`register_state_type` at module level
    immediately after defining that class. This ensures importing the provider
    module registers its state types before session restoration and before the
    provider itself is instantiated, without requiring consumer registration.
    Prefer JSON-native Python values when a custom runtime type is not needed
    after restoration.

    Attributes:
        load_messages: Whether to load messages before invocation (default True).
            When False, the agent skips calling ``before_run`` entirely.
        store_inputs: Whether to store input messages (default True).
        store_context_messages: Whether to store context from other providers (default False).
        store_context_from: If set, only store context from these source_ids.
        store_outputs: Whether to store response messages (default True).
    """

    def __init__(
        self,
        source_id: str,
        *,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: set[str] | None = None,
        store_outputs: bool = True,
    ):
        """Initialize the history provider.

        Args:
            source_id: Unique identifier for this provider instance.
            load_messages: Whether to load messages before invocation.
            store_inputs: Whether to store input messages.
            store_context_messages: Whether to store context from other providers.
            store_context_from: If set, only store context from these source_ids.
            store_outputs: Whether to store response messages.
        """
        super().__init__(source_id)
        self.load_messages = load_messages
        self.store_inputs = store_inputs
        self.store_context_messages = store_context_messages
        self.store_context_from = store_context_from
        self.store_outputs = store_outputs

    @abstractmethod
    async def get_messages(
        self, session_id: str | None, *, state: dict[str, Any] | None = None, **kwargs: Any
    ) -> list[Message]:
        """Retrieve stored messages for this session.

        Args:
            session_id: The session ID to retrieve messages for.
            state: Optional session state for providers that persist in session state.
                Not used by all providers.
            **kwargs: Additional subclass-specific extensibility arguments.

        Returns:
            List of stored messages.
        """
        ...

    @abstractmethod
    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Persist messages for this session.

        Args:
            session_id: The session ID to store messages for.
            messages: The messages to persist.
            state: Optional session state for providers that persist in session state.
                Not used by all providers.
            **kwargs: Additional subclass-specific extensibility arguments.
        """
        ...

    def _get_context_messages_to_store(self, context: SessionContext) -> list[Message]:
        """Get context messages that should be stored based on configuration."""
        if not self.store_context_messages:
            return []
        if self.store_context_from is not None:
            return context.get_messages(sources=self.store_context_from)
        return context.get_messages(exclude_sources={self.source_id})

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Load history into context. Skipped by the agent when load_messages=False."""
        history = _filter_approval_control_messages(await self.get_messages(context.session_id, state=state))
        context.extend_messages(self, history)

    async def after_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Store messages based on configuration."""
        messages_to_store: list[Message] = []
        messages_to_store.extend(self._get_context_messages_to_store(context))
        if self.store_inputs:
            messages_to_store.extend(context.input_messages)
        if self.store_outputs and context.response and context.response.messages:
            messages_to_store.extend(context.response.messages)
        if messages_to_store:
            await self.save_messages(context.session_id, messages_to_store, state=state)


LOCAL_HISTORY_CONVERSATION_ID = "agent_framework_local_history_persistence"


def is_local_history_conversation_id(conversation_id: str | None) -> bool:
    """Return whether a conversation id is the local history-persistence sentinel."""
    return conversation_id == LOCAL_HISTORY_CONVERSATION_ID


def _response_contains_follow_up_request(response: ChatResponse) -> bool:
    """Return whether a response requires another model call in the current run."""
    return any(
        item.type == "function_approval_request" or (item.type == "function_call" and not item.informational_only)
        for message in response.messages
        for item in message.contents
    )


def _split_service_call_messages(messages: Sequence[Message]) -> tuple[list[Message], dict[str, list[Message]]]:
    """Split service-call messages into input messages and attributed context messages."""
    input_messages: list[Message] = []
    context_messages: dict[str, list[Message]] = {}
    for message in messages:
        attribution = message.additional_properties.get("_attribution")
        if isinstance(attribution, Mapping):
            attribution_mapping = cast(Mapping[str, Any], attribution)
            source_id = attribution_mapping.get("source_id")
            if isinstance(source_id, str):
                context_messages.setdefault(source_id, []).append(message)
                continue
        input_messages.append(message)
    return input_messages, context_messages


def enqueue_messages(session: AgentSession, messages: AgentRunInputs) -> None:
    """Enqueue messages for the next model call in the given session.

    Args:
        session: The session whose pending message queue should receive the messages.
        messages: The messages to enqueue. Accepts the same flexible shapes as ``Agent.run`` input:
            a string, ``Content``, ``Message``, or a sequence of those.
    """
    pending_messages = normalize_messages(messages)
    if not pending_messages:
        return
    with _MESSAGE_INJECTION_LOCK:
        queue = cast(
            list[Message],
            session.state.setdefault(MESSAGE_INJECTION_PENDING_MESSAGES_STATE_KEY, []),
        )
        queue.extend(pending_messages)


class MessageInjectionMiddleware(ChatMiddleware):
    """Chat middleware that injects queued session messages into the model call loop.

    Messages can be enqueued for an :class:`AgentSession` before a run starts or while a run is in progress,
    including from tool code that receives a :class:`FunctionInvocationContext`. Pending messages are stored in
    ``session.state`` and drained into the next model call for that session. After a model call completes, the
    middleware loops internally only when there are newly queued messages and the response does not contain function
    calls that the function invocation layer must handle.
    """

    def __init__(self) -> None:
        """Initialize the middleware."""

    def enqueue_messages(self, session: AgentSession, messages: AgentRunInputs) -> None:
        """Enqueue messages for the next model call in the given session.

        Args:
            session: The session whose pending message queue should receive the messages.
            messages: The messages to enqueue. Accepts the same flexible shapes as ``Agent.run`` input:
                a string, ``Content``, ``Message``, or a sequence of those.
        """
        enqueue_messages(session, messages)

    def get_pending_messages(self, session: AgentSession) -> list[Message]:
        """Return a snapshot of messages queued for the given session.

        Args:
            session: The session whose pending messages should be returned.

        Returns:
            A point-in-time copy of the queued messages. The returned list is not updated if the queue is later
            drained or extended.
        """
        with _MESSAGE_INJECTION_LOCK:
            return list(cast(list[Message], session.state.get(MESSAGE_INJECTION_PENDING_MESSAGES_STATE_KEY, [])))

    def _drain_pending_messages(self, session: AgentSession, messages: Sequence[Message]) -> list[Message]:
        with _MESSAGE_INJECTION_LOCK:
            queue = cast(
                list[Message],
                session.state.setdefault(MESSAGE_INJECTION_PENDING_MESSAGES_STATE_KEY, []),
            )
            if not queue:
                return list(messages)
            next_messages = [*messages, *queue]
            queue.clear()
            return next_messages

    def _has_pending_messages(self, session: AgentSession) -> bool:
        with _MESSAGE_INJECTION_LOCK:
            return bool(session.state.get(MESSAGE_INJECTION_PENDING_MESSAGES_STATE_KEY, []))

    @staticmethod
    def _update_context_conversation_id(context: ChatContext, conversation_id: str | None) -> None:
        if conversation_id is None:
            return
        context.kwargs["conversation_id"] = conversation_id
        if context.options is None:
            context.options = {"conversation_id": conversation_id}
            return
        context.options = {**context.options, "conversation_id": conversation_id}

    async def _process_non_streaming(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
        session: AgentSession,
    ) -> None:
        while True:
            context.messages = self._drain_pending_messages(session, context.messages)
            context.result = None
            await call_next()
            if context.result is None:
                return
            if isinstance(context.result, ResponseStream):
                raise ValueError("Non-streaming message injection middleware requires a ChatResponse result.")
            response = cast(ChatResponse, context.result)
            if _response_contains_follow_up_request(response) or not self._has_pending_messages(session):
                return
            self._update_context_conversation_id(context, response.conversation_id)
            empty_messages: list[Message] = []
            context.messages = empty_messages

    async def _stream_injected_messages(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
        session: AgentSession,
    ) -> AsyncIterable[ChatResponseUpdate]:
        while True:
            context.messages = self._drain_pending_messages(session, context.messages)
            context.result = None
            await call_next()
            if context.result is None:
                return
            if not isinstance(context.result, ResponseStream):
                raise ValueError("Streaming message injection middleware requires a ResponseStream result.")
            stream = cast(ResponseStream[ChatResponseUpdate, ChatResponse], context.result)
            async for update in stream:
                yield update
            response = await stream.get_final_response()
            if _response_contains_follow_up_request(response) or not self._has_pending_messages(session):
                return
            self._update_context_conversation_id(context, response.conversation_id)
            empty_messages: list[Message] = []
            context.messages = empty_messages

    async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        """Inject pending session messages into chat model calls.

        Args:
            context: The chat invocation context for the current model call.
            call_next: The next middleware or leaf chat client.

        Raises:
            ChatClientInvalidRequestException: If the middleware is used without an active ``AgentSession``.
            ValueError: If downstream middleware returns a non-streaming result for streaming mode, or vice versa.
        """
        session = context.session
        if session is None:
            raise ChatClientInvalidRequestException(
                "MessageInjectionMiddleware requires an AgentSession. Pass session=... when running the agent."
            )

        if not context.stream:
            await self._process_non_streaming(context, call_next, session)
            return

        response_format = context.options.get("response_format") if context.options is not None else None
        context.result = ResponseStream(
            self._stream_injected_messages(context, call_next, session),
            finalizer=lambda updates: ChatResponse.from_updates(updates, output_format_type=response_format),
        )


class PerServiceCallHistoryPersistingMiddleware(ChatMiddleware):
    """Persist local chat history after each service call when history is framework-managed.

    This middleware runs around each model call when
    ``require_per_service_call_history_persistence`` is enabled. It loads history providers
    before the model call, persists them after the model call, and uses a local
    sentinel conversation id so the function loop follows the existing
    service-managed branch without forwarding that sentinel to the leaf client.
    """

    def __init__(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        providers: Sequence[HistoryProvider],
        service_stores_history: bool = False,
    ) -> None:
        """Initialize the middleware.

        Args:
            agent: The agent that owns the history providers.
            session: The active session for the current run.
            providers: The history providers participating in per-service-call persistence.
            service_stores_history: When True, the chat client stores history server-side. The
                middleware then skips loading providers and leaves the real conversation id
                untouched, persisting each service call without driving the function loop with a
                local sentinel. When False, the middleware loads providers and uses a local
                sentinel conversation id so the function loop runs without service-side storage.
        """
        self._agent = agent
        self._session = session
        self._providers = list(providers)
        self._service_stores_history = service_stores_history

    async def _prepare_service_call_context(self, messages: Sequence[Message]) -> SessionContext:
        """Create a per-call SessionContext and load history providers into it."""
        input_messages, context_messages = _split_service_call_messages(messages)
        service_call_context = SessionContext(
            session_id=self._session.session_id,
            service_session_id=None,
            input_messages=list(input_messages),
        )
        for source_id, source_messages in context_messages.items():
            service_call_context.extend_messages(source_id, source_messages)
        # When the service stores history, it owns loading; the providers are write-only sinks.
        if self._service_stores_history:
            return service_call_context
        for provider in self._providers:
            if not provider.load_messages:
                continue
            await provider.before_run(
                agent=self._agent,
                session=self._session,
                context=service_call_context,
                state=self._session.state.setdefault(provider.source_id, {}),
            )
        return service_call_context

    async def _persist_service_call_response(
        self,
        *,
        service_call_context: SessionContext,
        response: ChatResponse,
    ) -> None:
        """Persist a single model-call response through the configured history providers."""
        service_call_context._response = _build_agent_response_from_chat_response(  # type: ignore[assignment]
            response,
            suppress_response_id=True,
        )
        for provider in reversed(self._providers):
            await provider.after_run(
                agent=self._agent,
                session=self._session,
                context=service_call_context,
                state=self._session.state.setdefault(provider.source_id, {}),
            )

    def _strip_local_conversation_id(self, context: ChatContext) -> None:
        """Remove the local sentinel before the leaf chat client is invoked."""
        if is_local_history_conversation_id(cast(str | None, context.kwargs.get("conversation_id"))):
            context.kwargs.pop("conversation_id", None)

        if context.options is None:
            return

        mutable_options = dict(context.options)
        if is_local_history_conversation_id(cast(str | None, mutable_options.get("conversation_id"))):
            mutable_options.pop("conversation_id", None)
        context.options = mutable_options

    async def _finalize_response(
        self,
        *,
        service_call_context: SessionContext,
        response: ChatResponse,
    ) -> ChatResponse:
        """Persist a model response and apply the local follow-up sentinel when needed."""
        if (
            not self._service_stores_history
            and response.conversation_id is not None
            and not is_local_history_conversation_id(response.conversation_id)
        ):
            raise ChatClientInvalidResponseException(
                "require_per_service_call_history_persistence cannot be used "
                "when the chat client returns a real conversation_id."
            )

        # In storing mode the service is expected to echo a conversation id that the next run
        # resumes from. If it comes back empty, the provider still captures this turn but there is
        # no service id to load from next time, so cross-turn history can be lost silently. Warn
        # every time so this uncommon, easy-to-miss failure mode cannot fail quietly.
        if self._service_stores_history and response.conversation_id is None:
            logger.warning(
                "require_per_service_call_history_persistence is enabled with a chat client that "
                "stores history server-side, but the client returned no conversation_id; cross-turn "
                "history may not resume. Set store=False to load and resume from the HistoryProvider "
                "instead."
            )

        await self._persist_service_call_response(
            service_call_context=service_call_context,
            response=response,
        )
        # The local sentinel only applies when the service does not store history; when it does,
        # the real conversation id already drives function-loop continuation.
        if not self._service_stores_history and _response_contains_follow_up_request(response):
            response.mark_internal_conversation_id()
            response.conversation_id = LOCAL_HISTORY_CONVERSATION_ID
        return response

    async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        """Load and persist history providers around a single model call.

        Args:
            context: The chat invocation context for the current model call.
            call_next: The next middleware or the leaf chat client.

        Raises:
            ChatClientInvalidResponseException: If the leaf client returns a real
                service-managed conversation id while local per-service-call persistence is enabled.
            ValueError: If the downstream middleware contract returns the wrong
                result type for streaming or non-streaming execution.
        """
        service_call_context = await self._prepare_service_call_context(context.messages)
        # When the service stores history, leave the outgoing messages and the real conversation
        # id untouched (pass-through); the middleware only persists. Otherwise reconstruct the
        # outgoing messages from the loaded local history and strip the local sentinel.
        if not self._service_stores_history:
            context.messages = service_call_context.get_messages(include_input=True)
            self._strip_local_conversation_id(context)

        await call_next()

        if context.result is None:
            return

        if context.stream:
            if not isinstance(context.result, ResponseStream):
                raise ValueError("Streaming chat middleware requires a ResponseStream result.")
            context.result = context.result.with_result_hook(
                lambda response: self._finalize_response(
                    service_call_context=service_call_context,
                    response=response,
                )
            )
            return

        if isinstance(context.result, ResponseStream):
            raise ValueError("Non-streaming chat middleware requires a ChatResponse result.")
        context.result = await self._finalize_response(
            service_call_context=service_call_context,
            response=context.result,
        )


class AgentSession:
    """A conversation session with an agent.

    Lightweight state container. Provider instances are owned by the agent,
    not the session. The session only holds session IDs and a mutable state dict.

    ``service_session_id`` can contain a provider-issued service session
    identifier, such as a service conversation ID or response ID. Treat this
    value as trusted application state: it is scoped by the backing API key,
    service account, or project, but it is not an end-user authorization
    boundary by itself.

    Attributes:
        session_id: Unique identifier for this session.
        service_session_id: Service-managed session identifier
            (if using service-side storage).
        state: Mutable state dict shared with all providers.
    """

    def __init__(
        self,
        *,
        session_id: str | None = None,
        service_session_id: str | ServiceSessionId | None = None,
    ):
        """Initialize the session.

        Args:
            session_id: Optional session ID (generated if not provided).
            service_session_id: Optional service-managed session identifier.
        """
        self._session_id = session_id or str(uuid.uuid4())
        self.service_session_id = service_session_id
        self.state: dict[str, Any] = {}

    @property
    def session_id(self) -> str:
        """The unique identifier for this session."""
        return self._session_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize session to a plain dict for storage/transfer.

        Registered custom values use their configured codecs. Unregistered
        values defining ``to_dict`` retain the established dictionary behavior.
        Unregistered Pydantic models are still auto-registered temporarily but
        emit ``DeprecationWarning`` because cold-start restoration requires
        explicit module-level registration.
        """
        return {
            "type": "session",
            "session_id": self._session_id,
            "service_session_id": self.service_session_id,
            "state": _serialize_state(self.state),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentSession:
        """Restore session from a previously serialized dict.

        Values in ``state`` that were serialized via ``SerializationProtocol``
        (containing a ``type`` key) are restored to their original types.

        Args:
            data: Dict from a previous ``to_dict()`` call.

        Returns:
            Restored AgentSession instance.
        """
        session = cls(
            session_id=data["session_id"],
            service_session_id=data.get("service_session_id"),
        )
        session.state = _deserialize_state(data.get("state", {}))
        return session


@experimental(feature_id=ExperimentalFeature.SESSION_STORE)
class SessionStore:
    """In-memory storage for Agent Framework session snapshots.

    The store maps an opaque caller-selected ID to an :class:`AgentSession`.
    Reads return independent working copies so one continuation does not mutate
    another stored snapshot. The store has no eviction; callers that need TTLs,
    durable storage, or distributed coordination should provide another
    implementation with the same async methods.

    Session IDs are opaque non-empty strings. Custom implementations are
    responsible for applying any backend-specific key restrictions and must use
    parameterized queries and their backend's normal key-handling protections.
    """

    def __init__(self) -> None:
        """Create an empty session store."""
        self._sessions: dict[str, AgentSession] = {}

    @staticmethod
    def validate_session_id(session_id: str) -> None:
        """Validate an ID for use with a session store.

        Args:
            session_id: Session-store ID to validate.

        Raises:
            ValueError: If the ID is not a non-empty string.
        """
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id must be a non-empty string")

    async def get(self, session_id: str) -> AgentSession | None:
        """Return a copy of the stored session, or ``None`` when absent.

        Args:
            session_id: Opaque caller-selected session ID.

        Returns:
            An independent copy of the stored session, or ``None``.

        Raises:
            ValueError: If ``session_id`` is empty.
        """
        mark_feature_used(FeatureIndex.CORE_SESSION_STORE)
        SessionStore.validate_session_id(session_id)
        session = self._sessions.get(session_id)
        return copy.deepcopy(session) if session is not None else None

    async def set(self, session_id: str, session: AgentSession) -> None:
        """Store ``session`` under ``session_id``, replacing any existing entry.

        Args:
            session_id: Opaque caller-selected session ID.
            session: The session to store.

        Raises:
            ValueError: If ``session_id`` is empty.
        """
        mark_feature_used(FeatureIndex.CORE_SESSION_STORE)
        SessionStore.validate_session_id(session_id)
        self._sessions[session_id] = copy.deepcopy(session)

    async def delete(self, session_id: str) -> None:
        """Delete the stored session, if present.

        Args:
            session_id: Opaque caller-selected session ID.

        Raises:
            ValueError: If ``session_id`` is empty.
        """
        mark_feature_used(FeatureIndex.CORE_SESSION_STORE)
        SessionStore.validate_session_id(session_id)
        self._sessions.pop(session_id, None)


@experimental(feature_id=ExperimentalFeature.SESSION_STORE)
class FileSessionStore(SessionStore):
    """File-backed storage for Agent Framework session snapshots.

    Each session is stored as one JSON or MessagePack file beneath
    ``storage_path``. JSON is the default; pass ``serialization_format="msgpack"``
    for a compact binary representation.
    Writes use a unique sibling temporary file followed by :func:`os.replace`
    so readers never observe a partially written snapshot. Concurrent writers
    use last-writer-wins semantics.

    The complete snapshot is encoded and decoded in one call through a typed
    :mod:`msgspec` codec. The dynamic state mapping is routed through the
    explicit :func:`register_state_type` registry during encoding and restored
    after the typed envelope and snapshot version are validated.

    Security posture:
        Persisted session snapshots are stored as plaintext JSON or binary
        MessagePack on the local filesystem.
        Treat ``storage_path`` as trusted application storage, not as a secret
        store. Opaque store keys are encoded as portable filename stems, and
        resolved-path validation prevents path traversal via ``session_id``.
        These protections do not encrypt file contents or coordinate concurrent
        updates across processes or hosts. Process-local operations are
        serialized per file, and atomic replacement prevents partial writes;
        cross-process writers still use last-writer-wins semantics. Use OS-level
        file permissions, trusted directories, and carefully review what session
        state is allowed to be persisted.
    """

    MAX_SESSION_ID_LENGTH: ClassVar[int] = 128
    _FILE_LOCK_STRIPE_COUNT: ClassVar[int] = 64
    _FILE_OPERATION_LOCKS: ClassVar[tuple[threading.Lock, ...]] = tuple(
        threading.Lock() for _ in range(_FILE_LOCK_STRIPE_COUNT)
    )
    _ENCODED_SESSION_PREFIX: ClassVar[str] = "~session-"

    def __init__(
        self,
        storage_path: str | Path,
        *,
        serialization_format: Literal["json", "msgpack"] = "json",
    ) -> None:
        """Initialize file-backed session storage.

        Args:
            storage_path: Directory where session snapshot files are stored.

        Keyword Args:
            serialization_format: ``"json"`` (default) for readable JSON files
                or ``"msgpack"`` for binary MessagePack files.

        Raises:
            ValueError: If ``serialization_format`` is unsupported.
        """
        if serialization_format not in ("json", "msgpack"):
            raise ValueError("serialization_format must be 'json' or 'msgpack'")
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._storage_root = self.storage_path.resolve()
        self.serialization_format = serialization_format
        if serialization_format == "json":
            self._encoder = _SESSION_SNAPSHOT_ENCODER
            self._decoder = _SESSION_SNAPSHOT_DECODER
            self._file_extension = _JSON_FILE_EXTENSION
        else:
            self._encoder = _SESSION_SNAPSHOT_MSGPACK_ENCODER
            self._decoder = _SESSION_SNAPSHOT_MSGPACK_DECODER
            self._file_extension = _MSGPACK_FILE_EXTENSION

    async def get(self, session_id: str) -> AgentSession | None:
        """Load a session snapshot, or return ``None`` when it does not exist."""
        mark_feature_used(FeatureIndex.CORE_SESSION_STORE)
        file_path = self._session_file_path(session_id)
        file_lock = self._session_file_lock(file_path)

        def _read() -> AgentSession | None:
            with file_lock:
                try:
                    serialized = file_path.read_bytes()
                except FileNotFoundError:
                    return None
                try:
                    snapshot = self._decoder.decode(serialized)
                except msgspec.ValidationError as exc:
                    raise ValueError(f"Session snapshot '{file_path}' has an invalid schema.") from exc
                except msgspec.DecodeError as exc:
                    try:
                        quarantine_path = self._quarantine_corrupt_snapshot(file_path, serialized)
                    except OSError as quarantine_error:
                        raise ValueError(
                            f"Failed to deserialize session from '{file_path}', and the corrupt snapshot "
                            "could not be quarantined."
                        ) from quarantine_error
                    if quarantine_path is None:
                        raise ValueError(
                            f"Failed to deserialize session from '{file_path}'. "
                            "The snapshot changed while being read; retry."
                        ) from exc
                    raise ValueError(
                        f"Failed to deserialize session from '{file_path}'. The corrupt snapshot was quarantined to "
                        f"'{quarantine_path}'; retry to create a new session."
                    ) from exc
                if snapshot.version != _SESSION_SNAPSHOT_VERSION:
                    raise ValueError(
                        f"Unsupported session snapshot version {snapshot.version!r} in '{file_path}'; "
                        f"expected {_SESSION_SNAPSHOT_VERSION!r}."
                    )
                raw_state: object = snapshot.state
                if not isinstance(raw_state, dict):
                    raise ValueError(f"Session snapshot state in '{file_path}' must be a mapping.")
                try:
                    state = _deserialize_state(cast(dict[str, Any], raw_state))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Failed to restore session state from '{file_path}'.") from exc
                session = AgentSession(
                    session_id=snapshot.session_id,
                    service_session_id=snapshot.service_session_id,
                )
                session.state = state
                return session

        return await asyncio.to_thread(_read)

    async def set(self, session_id: str, session: AgentSession) -> None:
        """Persist a session snapshot atomically."""
        mark_feature_used(FeatureIndex.CORE_SESSION_STORE)
        file_path = self._session_file_path(session_id)
        file_lock = self._session_file_lock(file_path)
        if type(session) is not AgentSession:
            raise TypeError(
                "FileSessionStore supports AgentSession instances only; "
                "custom AgentSession subclasses require a custom SessionStore."
            )
        service_session_id = session.service_session_id
        serialized_service_session_id = (
            dict(service_session_id) if isinstance(service_session_id, Mapping) else service_session_id
        )
        snapshot = _SessionSnapshot(
            type="session",
            session_id=session.session_id,
            service_session_id=serialized_service_session_id,
            state=_SessionStatePayload(session.state),
        )
        serialized = self._encoder.encode(snapshot)

        def _write() -> None:
            with file_lock:
                temp_path = file_path.with_name(f".{file_path.name}.{uuid.uuid4().hex}.tmp")
                try:
                    temp_path.write_bytes(serialized)
                    os.replace(temp_path, file_path)
                finally:
                    temp_path.unlink(missing_ok=True)

        await asyncio.to_thread(_write)

    async def delete(self, session_id: str) -> None:
        """Delete a persisted session snapshot, if present."""
        mark_feature_used(FeatureIndex.CORE_SESSION_STORE)
        file_path = self._session_file_path(session_id)
        file_lock = self._session_file_lock(file_path)

        def _delete() -> None:
            with file_lock:
                file_path.unlink(missing_ok=True)

        await asyncio.to_thread(_delete)

    @staticmethod
    def validate_session_id(session_id: str) -> None:
        """Validate an ID for use as a built-in file-store key.

        Args:
            session_id: Session-store ID to validate.

        Raises:
            ValueError: If the ID is empty or too long.
        """
        SessionStore.validate_session_id(session_id)
        if len(session_id) > FileSessionStore.MAX_SESSION_ID_LENGTH:
            raise ValueError(f"session_id must be at most {FileSessionStore.MAX_SESSION_ID_LENGTH} characters")

    @staticmethod
    def _quarantine_corrupt_snapshot(file_path: Path, serialized: bytes) -> Path | None:
        """Move an unchanged corrupt snapshot aside so a retry can recover."""
        try:
            current_serialized = file_path.read_bytes()
        except FileNotFoundError:
            return None
        if current_serialized != serialized:
            return None
        quarantine_path = file_path.with_name(f".{file_path.name}.{uuid.uuid4().hex}.corrupt")
        os.replace(file_path, quarantine_path)
        return quarantine_path

    @classmethod
    def _session_file_lock(cls, file_path: Path) -> threading.Lock:
        """Return the process-local operation lock for a session file."""
        return cls._FILE_OPERATION_LOCKS[hash(file_path) % cls._FILE_LOCK_STRIPE_COUNT]

    def _session_file_path(self, session_id: str) -> Path:
        """Resolve the contained snapshot path for ``session_id``."""
        candidate_path = self._storage_root / self._session_file_name(session_id)
        file_path = candidate_path.resolve()
        if file_path != candidate_path or not file_path.is_relative_to(self._storage_root):
            raise ValueError(f"Session path escaped storage directory: {session_id!r}")
        return file_path

    def _session_file_name(self, session_id: str) -> str:
        """Return the portable snapshot filename for ``session_id``."""
        self.validate_session_id(session_id)
        file_stem = _session_file_stem(session_id, encoded_prefix=self._ENCODED_SESSION_PREFIX)
        return f"{file_stem}{self._file_extension}"


class InMemoryHistoryProvider(HistoryProvider):
    """Built-in history provider that stores messages in session.state.

    Messages are stored in ``state["messages"]`` as a list of
    ``Message`` objects. Serialization to/from dicts is handled by
    ``AgentSession.to_dict()``/``from_dict()`` using ``SerializationProtocol``.

    This provider holds no instance state — all data lives in the session's
    state dict, passed as a named ``state`` parameter to ``get_messages``/``save_messages``.

    This is the default provider auto-added by the agent for local sessions
    when no providers are configured and service-side storage is not requested.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "in_memory"

    def __init__(
        self,
        source_id: str | None = None,
        *,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: set[str] | None = None,
        store_outputs: bool = True,
        skip_excluded: bool = False,
    ) -> None:
        """Initialize the in-memory history provider.

        Args:
            source_id: Unique identifier for this provider instance.
                Defaults to DEFAULT_SOURCE_ID when not provided.
            load_messages: Whether to load messages before invocation.
            store_inputs: Whether to store input messages.
            store_context_messages: Whether to store context from other providers.
            store_context_from: If set, only store context from these source_ids.
            store_outputs: Whether to store response messages.
            skip_excluded: When True, ``get_messages`` omits messages whose
                ``additional_properties["_excluded"]`` is truthy. This is
                useful when a ``CompactionProvider`` marks messages as excluded
                in stored history and you want the loaded context to reflect
                those exclusions. Defaults to False (load all messages).
        """
        super().__init__(
            source_id=source_id or self.DEFAULT_SOURCE_ID,
            load_messages=load_messages,
            store_inputs=store_inputs,
            store_context_messages=store_context_messages,
            store_context_from=store_context_from,
            store_outputs=store_outputs,
        )
        self.skip_excluded = skip_excluded

    async def get_messages(
        self, session_id: str | None, *, state: dict[str, Any] | None = None, **kwargs: Any
    ) -> list[Message]:
        """Retrieve messages from session state."""
        mark_feature_used(FeatureIndex.CORE_IN_MEMORY_HISTORY_PROVIDER)
        if state is None:
            return []
        messages = list(state.get("messages", []))
        if self.skip_excluded:
            messages = [m for m in messages if not m.additional_properties.get("_excluded", False)]
        return messages

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Persist messages to session state."""
        mark_feature_used(FeatureIndex.CORE_IN_MEMORY_HISTORY_PROVIDER)
        if state is None:
            return
        existing = state.get("messages", [])
        state["messages"] = [*existing, *messages]


@experimental(feature_id=ExperimentalFeature.FILE_HISTORY)
class FileHistoryProvider(HistoryProvider):
    """File-backed history provider that stores one append-only file per session.

    JSON Lines is the default: each message is one JSON object per line.
    Pass ``serialization_format="msgpack"`` to store length-prefixed binary
    MessagePack records instead. Both formats use :mod:`msgspec` by default.
    The custom ``dumps`` and ``loads`` constructor arguments remain available
    for JSON Lines compatibility but are deprecated.

    Security posture:
        Persisted history is stored as plaintext JSONL or binary MessagePack on
        the local filesystem.
        Treat ``storage_path`` as trusted application storage, not as a secret
        store. Encoded fallback filenames and resolved-path validation help
        prevent path traversal via ``session_id``, but they do not encrypt file
        contents or provide cross-process / cross-host locking. Use OS-level
        file permissions, trusted directories, and carefully review what agent
        or tool output is allowed to be persisted.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "file_history"
    DEFAULT_SESSION_FILE_STEM: ClassVar[str] = "default"
    _FILE_LOCK_STRIPE_COUNT: ClassVar[int] = 64
    _ENCODED_SESSION_PREFIX: ClassVar[str] = "~session-"
    _MSGPACK_RECORD_HEADER_BYTES: ClassVar[int] = 4
    _MAX_MSGPACK_RECORD_BYTES: ClassVar[int] = 64 * 1024 * 1024
    _FILE_WRITE_LOCKS: ClassVar[tuple[threading.Lock, ...]] = tuple(
        threading.Lock() for _ in range(_FILE_LOCK_STRIPE_COUNT)
    )

    def __init__(
        self,
        storage_path: str | Path,
        *,
        source_id: str = DEFAULT_SOURCE_ID,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: set[str] | None = None,
        store_outputs: bool = True,
        skip_excluded: bool = False,
        serialization_format: Literal["json", "msgpack"] = "json",
        dumps: JsonDumps | None = None,
        loads: JsonLoads | None = None,
    ) -> None:
        """Initialize the file history provider.

        Args:
            storage_path: Directory path where session history files will be stored.

        Keyword Args:
            source_id: Unique identifier for this provider instance.
            load_messages: Whether to load messages before invocation.
            store_inputs: Whether to store input messages.
            store_context_messages: Whether to store context from other providers.
            store_context_from: If set, only store context from these source_ids.
            store_outputs: Whether to store response messages.
            skip_excluded: When True, ``get_messages`` omits messages whose
                ``additional_properties["_excluded"]`` is truthy.
            serialization_format: ``"json"`` (default) for JSON Lines or
                ``"msgpack"`` for length-prefixed binary MessagePack records.
            dumps: Deprecated. Callable that serializes a message payload dict
                to single-line JSON text or UTF-8 bytes. Omit this argument to
                use the built-in msgspec codec.
            loads: Deprecated. Callable that deserializes JSON text or bytes
                back to a message payload dict. Omit this argument to use the
                built-in msgspec codec.

        Raises:
            ValueError: If the format is unsupported or custom JSON codecs are
                supplied with MessagePack.
        """
        if serialization_format not in ("json", "msgpack"):
            raise ValueError("serialization_format must be 'json' or 'msgpack'")
        if serialization_format == "msgpack" and (dumps is not None or loads is not None):
            raise ValueError("Custom dumps and loads are supported only with serialization_format='json'")
        if dumps is not None or loads is not None:
            warnings.warn(
                "The FileHistoryProvider constructor arguments `dumps` and `loads` are deprecated and will be "
                "removed in a future version. Omit them to use the built-in msgspec codec selected by "
                "`serialization_format`.",
                DeprecationWarning,
                stacklevel=2,
            )
        super().__init__(
            source_id=source_id,
            load_messages=load_messages,
            store_inputs=store_inputs,
            store_context_messages=store_context_messages,
            store_context_from=store_context_from,
            store_outputs=store_outputs,
        )
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._storage_root = self.storage_path.resolve()
        self.skip_excluded = skip_excluded
        self.serialization_format = serialization_format
        self._file_extension = _JSON_LINES_FILE_EXTENSION if serialization_format == "json" else _MSGPACK_FILE_EXTENSION
        self.dumps = dumps or _default_json_dumps
        self.loads = loads or _default_json_loads
        self._async_write_locks_by_loop: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            tuple[asyncio.Lock, ...],
        ] = weakref.WeakKeyDictionary()

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        """Retrieve messages from the session's history file."""
        mark_feature_used(FeatureIndex.CORE_FILE_HISTORY_PROVIDER)
        del state, kwargs
        file_path = self._session_file_path(session_id)
        async_lock = self._session_async_write_lock(file_path)
        thread_lock = self._session_write_lock(file_path)

        def _read_messages() -> list[Message]:
            with thread_lock:
                if not file_path.exists():
                    return []

                if self.serialization_format == "json":
                    return self._read_json_messages(file_path)
                return self._read_msgpack_messages(file_path)

        async with async_lock:
            messages = await asyncio.to_thread(_read_messages)
        if self.skip_excluded:
            messages = [m for m in messages if not m.additional_properties.get("_excluded", False)]
        return messages

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Append messages to the session's history file."""
        mark_feature_used(FeatureIndex.CORE_FILE_HISTORY_PROVIDER)
        del state, kwargs
        if not messages:
            return

        file_path = self._session_file_path(session_id)
        async_lock = self._session_async_write_lock(file_path)
        file_lock = self._session_write_lock(file_path)

        def _append_messages() -> None:
            with file_lock:
                if self.serialization_format == "json":
                    with file_path.open("a", encoding="utf-8") as file_handle:
                        for message in messages:
                            file_handle.write(f"{self._serialize_json_message(message)}\n")
                    return
                with file_path.open("ab") as file_handle:
                    for message in messages:
                        serialized = _DEFAULT_MSGPACK_ENCODER.encode(message.to_dict())
                        file_handle.write(len(serialized).to_bytes(self._MSGPACK_RECORD_HEADER_BYTES, "big"))
                        file_handle.write(serialized)

        async with async_lock:
            await asyncio.to_thread(_append_messages)

    def _read_json_messages(self, file_path: Path) -> list[Message]:
        """Read JSON Lines messages from ``file_path``."""
        messages: list[Message] = []
        with file_path.open(encoding="utf-8") as file_handle:
            for line_number, line in enumerate(file_handle, start=1):
                serialized = line.strip()
                if not serialized:
                    continue
                try:
                    payload = self.loads(serialized)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Failed to deserialize history line {line_number} from '{file_path}'.") from exc
                messages.append(self._parse_message_payload(payload, file_path=file_path, record_number=line_number))
        return messages

    def _read_msgpack_messages(self, file_path: Path) -> list[Message]:
        """Read length-prefixed MessagePack records from ``file_path``."""
        messages: list[Message] = []
        with file_path.open("rb") as file_handle:
            record_number = 0
            while True:
                header = file_handle.read(self._MSGPACK_RECORD_HEADER_BYTES)
                if not header:
                    return messages
                record_number += 1
                if len(header) != self._MSGPACK_RECORD_HEADER_BYTES:
                    raise ValueError(f"History record {record_number} in '{file_path}' has a truncated length header.")
                record_length = int.from_bytes(header, "big")
                if record_length <= 0 or record_length > self._MAX_MSGPACK_RECORD_BYTES:
                    raise ValueError(
                        f"History record {record_number} in '{file_path}' has invalid length {record_length}."
                    )
                serialized = file_handle.read(record_length)
                if len(serialized) != record_length:
                    raise ValueError(f"History record {record_number} in '{file_path}' is truncated.")
                try:
                    payload = _DEFAULT_MSGPACK_DECODER.decode(serialized)
                except msgspec.DecodeError as exc:
                    raise ValueError(
                        f"Failed to deserialize history record {record_number} from '{file_path}'."
                    ) from exc
                messages.append(self._parse_message_payload(payload, file_path=file_path, record_number=record_number))

    @staticmethod
    def _parse_message_payload(payload: Any, *, file_path: Path, record_number: int) -> Message:
        """Validate and reconstruct one stored Message payload."""
        if not isinstance(payload, Mapping):
            raise ValueError(f"History record {record_number} in '{file_path}' did not deserialize to a mapping.")
        try:
            return Message.from_dict(dict(cast(Mapping[str, Any], payload)))
        except ValueError as exc:
            raise ValueError(
                f"History record {record_number} in '{file_path}' is not a valid Message payload."
            ) from exc

    def _serialize_json_message(self, message: Message) -> str:
        """Serialize a message payload to a single JSON Lines record."""
        serialized = self.dumps(message.to_dict())
        if isinstance(serialized, bytes):
            serialized_text = serialized.decode("utf-8")
        elif isinstance(serialized, str):
            serialized_text = serialized
        else:
            raise TypeError("FileHistoryProvider.dumps must return str or bytes.")

        if "\n" in serialized_text or "\r" in serialized_text:
            raise ValueError("FileHistoryProvider.dumps must return single-line JSON for JSON Lines storage.")
        return serialized_text

    def _session_file_path(self, session_id: str | None) -> Path:
        """Resolve the on-disk history file path for a session."""
        file_path = (self._storage_root / f"{self._session_file_stem(session_id)}{self._file_extension}").resolve()
        if not file_path.is_relative_to(self._storage_root):
            raise ValueError(f"Session history path escaped storage directory: {session_id!r}")
        return file_path

    def _session_file_stem(self, session_id: str | None) -> str:
        """Return the filename stem for a session."""
        raw_session_id = session_id or self.DEFAULT_SESSION_FILE_STEM
        return _session_file_stem(raw_session_id, encoded_prefix=self._ENCODED_SESSION_PREFIX)

    def _session_async_write_lock(self, file_path: Path) -> asyncio.Lock:
        """Return the event-loop-local async lock for a session history file."""
        loop = asyncio.get_running_loop()
        locks = self._async_write_locks_by_loop.get(loop)
        if locks is None:
            locks = tuple(asyncio.Lock() for _ in range(self._FILE_LOCK_STRIPE_COUNT))
            self._async_write_locks_by_loop[loop] = locks
        return locks[self._lock_index(file_path)]

    @classmethod
    def _session_write_lock(cls, file_path: Path) -> threading.Lock:
        """Return the process-local thread lock for a session history file."""
        return cls._FILE_WRITE_LOCKS[cls._lock_index(file_path)]

    @classmethod
    def _lock_index(cls, file_path: Path) -> int:
        """Map a session history file to a bounded lock stripe."""
        return hash(file_path) % cls._FILE_LOCK_STRIPE_COUNT

    @classmethod
    def _is_literal_session_file_stem_safe(cls, session_id: str) -> bool:
        """Return whether the session ID can be used directly as a filename stem."""
        return _is_literal_session_file_stem_safe(session_id)
