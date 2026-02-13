# Copyright (c) Microsoft. All rights reserved.

"""Unified context management types for the agent framework.

This module provides the core types for the context provider pipeline:
- SessionContext: Per-invocation state passed through providers
- BaseContextProvider: Base class for context providers (renamed to ContextProvider in PR2)
- BaseHistoryProvider: Base class for history storage providers (renamed to HistoryProvider in PR2)
- AgentSession: Lightweight session state container
- InMemoryHistoryProvider: Built-in in-memory history provider
"""

from __future__ import annotations

import copy
import uuid
from abc import abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ._types import AgentResponse, Message

if TYPE_CHECKING:
    from ._agents import SupportsAgentRun


# Registry of known types for state deserialization
_STATE_TYPE_REGISTRY: dict[str, type] = {}


def register_state_type(cls: type) -> None:
    """Register a type for automatic deserialization in session state.

    Call this for any custom type (including Pydantic models) that you store
    in ``session.state`` and want to survive ``to_dict()`` / ``from_dict()``
    round-trips. Types with ``to_dict``/``from_dict`` methods or Pydantic
    ``BaseModel`` subclasses are handled automatically.

    The type identifier defaults to ``cls.__name__.lower()`` but can be
    overridden by defining a ``_get_type_identifier`` classmethod.

    Note:
        Pydantic models are auto-registered on first serialization, but
        pre-registering ensures deserialization works even if the model
        hasn't been serialized in this process yet (e.g. cold-start restore).

    Args:
        cls: The type to register.
    """
    type_id: str = getattr(cls, "_get_type_identifier", lambda: cls.__name__.lower())()
    _STATE_TYPE_REGISTRY[type_id] = cls


# Keep internal alias for framework use
_register_state_type = register_state_type


def _serialize_value(value: Any) -> Any:
    """Serialize a single value, handling objects with to_dict() and Pydantic models."""
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()  # pyright: ignore[reportUnknownMemberType]
    # Pydantic BaseModel support — import lazily to avoid hard dep at module level
    try:
        from pydantic import BaseModel

        if isinstance(value, BaseModel):
            data = value.model_dump()
            type_id: str = getattr(value.__class__, "_get_type_identifier", lambda: value.__class__.__name__.lower())()
            data["type"] = type_id
            # Auto-register for round-trip deserialization
            _STATE_TYPE_REGISTRY.setdefault(type_id, value.__class__)
            return data
    except ImportError:
        pass
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return value


def _deserialize_value(value: Any) -> Any:
    """Deserialize a single value, restoring registered types."""
    if isinstance(value, dict) and "type" in value:
        type_id = str(value["type"])  # pyright: ignore[reportUnknownArgumentType]
        cls = _STATE_TYPE_REGISTRY.get(type_id)
        if cls is not None:
            if hasattr(cls, "from_dict"):
                return cls.from_dict(value)  # type: ignore[union-attr]
            # Pydantic BaseModel support
            try:
                from pydantic import BaseModel

                if issubclass(cls, BaseModel):
                    data = {k: v for k, v in value.items() if k != "type"}
                    return cls.model_validate(data)
            except ImportError:
                pass
    if isinstance(value, list):
        return [_deserialize_value(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, dict):
        return {str(k): _deserialize_value(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return value


def _serialize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Deep-serialize a state dict, converting SerializationProtocol objects to dicts."""
    return {k: _serialize_value(v) for k, v in state.items()}


def _deserialize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Deep-deserialize a state dict, restoring SerializationProtocol objects."""
    return {k: _deserialize_value(v) for k, v in state.items()}


# Register known types
_register_state_type(Message)


class SessionContext:
    """Per-invocation state passed through the context provider pipeline.

    Created fresh for each agent.run() call. Providers read from and write to
    the mutable fields to add context before invocation and process responses after.

    Attributes:
        session_id: The ID of the current session.
        service_session_id: Service-managed session ID (if present, service handles storage).
        input_messages: The new messages being sent to the agent (set by caller).
        context_messages: Dict mapping source_id -> messages added by that provider.
            Maintains insertion order (provider execution order).
        instructions: Additional instructions added by providers.
        tools: Additional tools added by providers.
        response: After invocation, contains the full AgentResponse, should not be changed.
        options: Options passed to agent.run() - read-only, for reflection only.
        metadata: Shared metadata dictionary for cross-provider communication.
    """

    def __init__(
        self,
        *,
        session_id: str | None = None,
        service_session_id: str | None = None,
        input_messages: list[Message],
        context_messages: dict[str, list[Message]] | None = None,
        instructions: list[str] | None = None,
        tools: list[Any] | None = None,
        options: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize the session context.

        Args:
            session_id: The ID of the current session.
            service_session_id: Service-managed session ID.
            input_messages: The new messages being sent to the agent.
            context_messages: Pre-populated context messages by source.
            instructions: Pre-populated instructions.
            tools: Pre-populated tools.
            options: Options from agent.run() - read-only for providers.
            metadata: Shared metadata for cross-provider communication.
        """
        self.session_id = session_id
        self.service_session_id = service_session_id
        self.input_messages = input_messages
        self.context_messages: dict[str, list[Message]] = context_messages or {}
        self.instructions: list[str] = instructions or []
        self.tools: list[Any] = tools or []
        self._response: AgentResponse | None = None
        self.options: dict[str, Any] = options or {}
        self.metadata: dict[str, Any] = metadata or {}

    @property
    def response(self) -> AgentResponse | None:
        """The agent's response. Set by the framework after invocation, read-only for providers."""
        return self._response

    def extend_messages(self, source: str | object, messages: Sequence[Message]) -> None:
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
        """
        if isinstance(source, str):
            source_id = source
            attribution: dict[str, str] = {"source_id": source_id}
        else:
            source_id = source.source_id  # type: ignore[attr-defined]
            attribution = {"source_id": source_id, "source_type": type(source).__name__}

        copied: list[Message] = []
        for message in messages:
            msg_copy = copy.copy(message)
            msg_copy.additional_properties = dict(message.additional_properties)
            msg_copy.additional_properties.setdefault("_attribution", attribution)
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
            if hasattr(tool, "additional_properties") and isinstance(tool.additional_properties, dict):
                tool.additional_properties["context_source"] = source_id
        self.tools.extend(tools)

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


class BaseContextProvider:
    """Base class for context providers (hooks pattern).

    Context providers participate in the context engineering pipeline,
    adding context before model invocation and processing responses after.

    Note:
        This class uses a temporary name prefixed with ``_`` to avoid collision
        with the existing ``ContextProvider`` in ``_memory.py``. It will be
        renamed to ``ContextProvider`` in PR2 when the old class is removed.

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
            context: The invocation context - add messages/instructions/tools here.
            state: The session's mutable state dict.
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
            state: The session's mutable state dict.
        """


class BaseHistoryProvider(BaseContextProvider):
    """Base class for conversation history storage providers.

    A single class configurable for different use cases:
    - Primary memory storage (loads + stores messages)
    - Audit/logging storage (stores only, doesn't load)
    - Evaluation storage (stores only for later analysis)

    Note:
        This class uses a temporary name prefixed with ``_`` to avoid collision
        with existing types. It will be renamed to ``HistoryProvider`` in PR2.

    Subclasses only need to implement ``get_messages()`` and ``save_messages()``.
    The default ``before_run``/``after_run`` handle loading and storing based on
    configuration flags. Override them for custom behavior.

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
    async def get_messages(self, session_id: str | None, **kwargs: Any) -> list[Message]:
        """Retrieve stored messages for this session.

        Args:
            session_id: The session ID to retrieve messages for.
            **kwargs: Additional arguments (e.g., ``state`` for in-memory providers).

        Returns:
            List of stored messages.
        """
        ...

    @abstractmethod
    async def save_messages(self, session_id: str | None, messages: Sequence[Message], **kwargs: Any) -> None:
        """Persist messages for this session.

        Args:
            session_id: The session ID to store messages for.
            messages: The messages to persist.
            **kwargs: Additional arguments (e.g., ``state`` for in-memory providers).
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
        history = await self.get_messages(context.session_id, state=state)
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


class AgentSession:
    """A conversation session with an agent.

    Lightweight state container. Provider instances are owned by the agent,
    not the session. The session only holds session IDs and a mutable state dict.

    Attributes:
        session_id: Unique identifier for this session.
        service_session_id: Service-managed session ID (if using service-side storage).
        state: Mutable state dict shared with all providers.
    """

    def __init__(
        self,
        *,
        session_id: str | None = None,
        service_session_id: str | None = None,
    ):
        """Initialize the session.

        Args:
            session_id: Optional session ID (generated if not provided).
            service_session_id: Optional service-managed session ID.
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

        Values in ``state`` that implement ``SerializationProtocol`` (i.e. have
        ``to_dict``/``from_dict``) are serialized automatically. Built-in types
        (str, int, float, bool, None, list, dict) are kept as-is.
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


class InMemoryHistoryProvider(BaseHistoryProvider):
    """Built-in history provider that stores messages in session.state.

    Messages are stored in ``state[source_id]["messages"]`` as a list of
    ``Message`` objects. Serialization to/from dicts is handled by
    ``AgentSession.to_dict()``/``from_dict()`` using ``SerializationProtocol``.

    This provider holds no instance state — all data lives in the session's
    state dict, passed as a named ``state`` parameter to ``get_messages``/``save_messages``.

    This is the default provider auto-added by the agent when no providers
    are configured and ``conversation_id`` or ``store=True`` is set.
    """

    async def get_messages(
        self, session_id: str | None, *, state: dict[str, Any] | None = None, **kwargs: Any
    ) -> list[Message]:
        """Retrieve messages from session state."""
        if state is None:
            return []
        my_state = state.get(self.source_id, {})
        return list(my_state.get("messages", []))

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Persist messages to session state."""
        if state is None:
            return
        my_state = state.setdefault(self.source_id, {})
        existing = my_state.get("messages", [])
        my_state["messages"] = [*existing, *messages]
