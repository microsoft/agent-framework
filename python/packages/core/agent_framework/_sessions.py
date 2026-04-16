# Copyright (c) Microsoft. All rights reserved.

"""Unified context management types for the agent framework.

This module provides the core types for the context provider pipeline:
- SessionContext: Per-invocation state passed through providers
- ContextProvider: Base class for context providers
- HistoryProvider: Base class for history storage providers
- AgentSession: Lightweight session state container
- InMemoryHistoryProvider: Built-in in-memory history provider
- FileHistoryProvider: Built-in JSON Lines file history provider
"""

from __future__ import annotations

import asyncio
import copy
import json
import threading
import uuid
import weakref
from abc import abstractmethod
from base64 import urlsafe_b64encode
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, TypeAlias, TypeGuard, cast

from ._feature_stage import ExperimentalFeature, experimental
from ._middleware import ChatContext, ChatMiddleware
from ._types import AgentResponse, ChatResponse, Message, ResponseStream
from .exceptions import ChatClientInvalidResponseException

if TYPE_CHECKING:
    from ._agents import SupportsAgentRun
    from ._middleware import MiddlewareTypes


# Registry of known types for state deserialization
_STATE_TYPE_REGISTRY: dict[str, type] = {}

JsonDumps: TypeAlias = Callable[[Any], str | bytes]
JsonLoads: TypeAlias = Callable[[str | bytes], Any]


def _default_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _default_json_loads(value: str | bytes) -> Any:
    return json.loads(value)


def _is_middleware_sequence(
    middleware: MiddlewareTypes | Sequence[MiddlewareTypes],
) -> TypeGuard[Sequence[MiddlewareTypes]]:
    return isinstance(middleware, Sequence) and not isinstance(middleware, (str, bytes))


def _is_single_middleware(
    middleware: MiddlewareTypes | Sequence[MiddlewareTypes],
) -> TypeGuard[MiddlewareTypes]:
    return not _is_middleware_sequence(middleware)


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
                    data: dict[str, Any] = {str(k): v for k, v in value.items() if k != "type"}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
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
        service_session_id: str | None = None,
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
            service_session_id: Service-managed session ID.
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


class HistoryProvider(ContextProvider):
    """Base class for conversation history storage providers.

    A single class configurable for different use cases:
    - Primary memory storage (loads + stores messages)
    - Audit/logging storage (stores only, doesn't load)
    - Evaluation storage (stores only for later analysis)

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


LOCAL_HISTORY_CONVERSATION_ID = "agent_framework_local_history_persistence"


def is_local_history_conversation_id(conversation_id: str | None) -> bool:
    """Return whether a conversation id is the local history-persistence sentinel."""
    return conversation_id == LOCAL_HISTORY_CONVERSATION_ID


def _response_contains_follow_up_request(response: ChatResponse) -> bool:
    """Return whether a response requires another model call in the current run."""
    return any(
        item.type in {"function_call", "function_approval_request"}
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
    ) -> None:
        """Initialize the middleware.

        Args:
            agent: The agent that owns the history providers.
            session: The active session for the current run.
            providers: The history providers participating in per-service-call persistence.
        """
        self._agent = agent
        self._session = session
        self._providers = list(providers)

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
        service_call_context._response = AgentResponse(  # type: ignore[assignment]
            messages=response.messages,
            response_id=None,
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
        if response.conversation_id is not None and not is_local_history_conversation_id(response.conversation_id):
            raise ChatClientInvalidResponseException(
                "require_per_service_call_history_persistence cannot be used "
                "when the chat client returns a real conversation_id."
            )

        await self._persist_service_call_response(
            service_call_context=service_call_context,
            response=response,
        )
        if _response_contains_follow_up_request(response):
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
        if state is None:
            return
        existing = state.get("messages", [])
        state["messages"] = [*existing, *messages]


@experimental(feature_id=ExperimentalFeature.FILE_HISTORY)
class FileHistoryProvider(HistoryProvider):
    """File-backed history provider that stores one JSON Lines file per session.

    Each persisted message is written as a single JSON object per line. The
    provider does not serialize full session snapshots into the file. By default
    it uses the standard library ``json`` module, but callers can inject
    alternative ``dumps`` and ``loads`` callables compatible with the JSON
    Lines format.

    Security posture:
        Persisted history is stored as plaintext JSONL on the local filesystem.
        Treat ``storage_path`` as trusted application storage, not as a secret
        store. Encoded fallback filenames and resolved-path validation help
        prevent path traversal via ``session_id``, but they do not encrypt file
        contents or provide cross-process / cross-host locking. Use OS-level
        file permissions, trusted directories, and carefully review what agent
        or tool output is allowed to be persisted.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "file_history"
    DEFAULT_SESSION_FILE_STEM: ClassVar[str] = "default"
    FILE_EXTENSION: ClassVar[str] = ".jsonl"
    _FILE_LOCK_STRIPE_COUNT: ClassVar[int] = 64
    _ENCODED_SESSION_PREFIX: ClassVar[str] = "~session-"
    _FILE_WRITE_LOCKS: ClassVar[tuple[threading.Lock, ...]] = tuple(
        threading.Lock() for _ in range(_FILE_LOCK_STRIPE_COUNT)
    )
    _WINDOWS_RESERVED_FILE_STEMS: ClassVar[frozenset[str]] = frozenset({
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
    })

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
            dumps: Callable that serializes a message payload dict to JSON text
                or UTF-8 bytes. The returned JSON must fit on a single line.
            loads: Callable that deserializes JSON text or bytes back to a
                message payload dict.
        """
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
        """Retrieve messages from the session's JSON Lines file."""
        del state, kwargs
        file_path = self._session_file_path(session_id)
        async_lock = self._session_async_write_lock(file_path)
        thread_lock = self._session_write_lock(file_path)

        def _read_messages() -> list[Message]:
            with thread_lock:
                if not file_path.exists():
                    return []

                messages: list[Message] = []
                with file_path.open(encoding="utf-8") as file_handle:
                    for line_number, line in enumerate(file_handle, start=1):
                        serialized = line.strip()
                        if not serialized:
                            continue
                        try:
                            payload = self.loads(serialized)
                        except (TypeError, ValueError) as exc:
                            raise ValueError(
                                f"Failed to deserialize history line {line_number} from '{file_path}'."
                            ) from exc
                        if not isinstance(payload, Mapping):
                            raise ValueError(
                                f"History line {line_number} in '{file_path}' did not deserialize to a mapping."
                            )

                        try:
                            message = Message.from_dict(dict(cast(Mapping[str, Any], payload)))
                        except ValueError as exc:
                            raise ValueError(
                                f"History line {line_number} in '{file_path}' is not a valid Message payload."
                            ) from exc
                        messages.append(message)
                return messages

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
        """Append messages to the session's JSON Lines file."""
        del state, kwargs
        if not messages:
            return

        file_path = self._session_file_path(session_id)
        async_lock = self._session_async_write_lock(file_path)
        file_lock = self._session_write_lock(file_path)

        def _append_messages() -> None:
            with file_lock, file_path.open("a", encoding="utf-8") as file_handle:
                for message in messages:
                    file_handle.write(f"{self._serialize_message(message)}\n")

        async with async_lock:
            await asyncio.to_thread(_append_messages)

    def _serialize_message(self, message: Message) -> str:
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
        file_path = (self._storage_root / f"{self._session_file_stem(session_id)}{self.FILE_EXTENSION}").resolve()
        if not file_path.is_relative_to(self._storage_root):
            raise ValueError(f"Session history path escaped storage directory: {session_id!r}")
        return file_path

    def _session_file_stem(self, session_id: str | None) -> str:
        """Return the filename stem for a session."""
        raw_session_id = session_id or self.DEFAULT_SESSION_FILE_STEM
        if self._is_literal_session_file_stem_safe(raw_session_id):
            return raw_session_id

        encoded_session_id = urlsafe_b64encode(raw_session_id.encode("utf-8")).decode("ascii").rstrip("=")
        return f"{self._ENCODED_SESSION_PREFIX}{encoded_session_id or self.DEFAULT_SESSION_FILE_STEM}"

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
        if (
            not session_id
            or session_id.startswith(".")
            or session_id.endswith((" ", "."))
            or session_id.upper() in cls._WINDOWS_RESERVED_FILE_STEMS
        ):
            return False
        if any(ord(character) < 32 for character in session_id):
            return False
        return all(character.isalnum() or character in "._-" for character in session_id)
