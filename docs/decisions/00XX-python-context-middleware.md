---
# These are optional elements. Feel free to remove any of them.
status: proposed
contact: eavanvalkenburg
date: 2026-02-02
deciders: eavanvalkenburg, markwallace-microsoft, sphenry, alliscode, johanst, brettcannon
consulted: taochenosu, moonbox3, dmytrostruk, giles17
---

# Unifying Context Management with ContextMiddleware

## Context and Problem Statement

The Agent Framework Python SDK currently has multiple abstractions for managing conversation context:

| Concept | Purpose | Location |
|---------|---------|----------|
| `ContextProvider` | Injects instructions, messages, and tools before/after invocations | `_memory.py` |
| `ChatMessageStore` / `ChatMessageStoreProtocol` | Stores and retrieves conversation history | `_threads.py` |
| `AgentThread` | Manages conversation state and coordinates storage | `_threads.py` |

This creates cognitive overhead for developers doing "Context Engineering" - the practice of dynamically managing what context (history, RAG results, instructions, tools) is sent to the model. Users must understand:
- When to use `ContextProvider` vs `ChatMessageStore`
- How `AgentThread` coordinates between them
- Different lifecycle hooks (`invoking()`, `invoked()`, `thread_created()`)

**How can we simplify context management into a single, composable pattern that handles all context-related concerns?**

## Decision Drivers

- **Simplicity**: Reduce the number of concepts users must learn
- **Composability**: Enable multiple context sources to be combined flexibly
- **Consistency**: Follow existing patterns in the framework (middleware)
- **Flexibility**: Support both stateless and session-specific middleware
- **Attribution**: Enable tracking which middleware added which messages/tools
- **Zero-config**: Simple use cases should work without configuration

## Current State Analysis

### ContextProvider (Current)

```python
class ContextProvider(ABC):
    async def thread_created(self, thread_id: str | None) -> None:
        """Called when a new thread is created."""
        pass

    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Called after the agent receives a response."""
        pass

    @abstractmethod
    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        """Called before model invocation. Returns Context with instructions, messages, tools."""
        pass
```

**Limitations:**
- Separate `invoking()` and `invoked()` methods make pre/post processing awkward
- Returns a `Context` object that must be merged externally
- No clear way to compose multiple providers
- No source attribution for debugging

### ChatMessageStore (Current)

```python
class ChatMessageStoreProtocol(Protocol):
    async def list_messages(self) -> list[ChatMessage]: ...
    async def add_messages(self, messages: Sequence[ChatMessage]) -> None: ...
    async def serialize(self, **kwargs: Any) -> dict[str, Any]: ...
    @classmethod
    async def deserialize(cls, state: MutableMapping[str, Any], **kwargs: Any) -> "ChatMessageStoreProtocol": ...
```

**Limitations:**
- Only handles storage, no context injection
- Separate concept from `ContextProvider`
- No control over what gets stored (RAG context vs user messages)

### AgentThread (Current)

```python
class AgentThread:
    def __init__(
        self,
        *,
        service_thread_id: str | None = None,
        message_store: ChatMessageStoreProtocol | None = None,
        context_provider: ContextProvider | None = None,
    ) -> None: ...
```

**Limitations:**
- Coordinates storage and context separately
- Only one `context_provider` (no composition)
- Naming confusion (`Thread` vs `Session`)

## Design Decisions Summary

The following key decisions shape the ContextMiddleware design:

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Agent vs Session Ownership** | Agent owns middleware config; Session owns resolved pipeline. Enables per-session factories. |
| 2 | **Instance or Factory** | Middleware can be shared instances or `(session_id) -> Middleware` factories for per-session state. |
| 3 | **Default Storage at Runtime** | `InMemoryStorageMiddleware` auto-added when no service_session_id, store≠True, and no pipeline. Evaluated at runtime so users can modify pipeline first. |
| 4 | **Multiple Storage Allowed** | Warn if multiple have `load_messages=True` (likely misconfiguration). |
| 5 | **Single Storage Class** | One `StorageContextMiddleware` configured for memory/audit/evaluation - no separate classes. |
| 6 | **Mandatory source_id** | Required parameter forces explicit naming for attribution in `context_messages` dict. |
| 7 | **Smart Load Behavior** | `load_messages=None` (default) disables loading when `options.store=False` OR `service_session_id` present. |
| 8 | **Dict-based Context** | `context_messages: dict[str, list[ChatMessage]]` keyed by source_id maintains order and enables filtering. |
| 9 | **Selective Storage** | `store_context_messages` and `store_context_from` control what gets persisted from other middleware. |
| 10 | **Tool Attribution** | `add_tools()` automatically sets `tool.metadata["context_source"] = source_id`. |
| 11 | **Clean Break** | Remove `AgentThread`, `ContextProvider`, `ChatMessageStore` completely (preview, no compatibility shims). |
| 12 | **Middleware Ordering** | User-defined order; storage sees prior middleware (pre-processing) or all middleware (post-processing). |

## Considered Options

### Option 1: Status Quo - Keep Separate Abstractions

Keep `ContextProvider`, `ChatMessageStore`, and `AgentThread` as separate concepts.

**Pros:**
- No migration required
- Familiar to existing users

**Cons:**
- Cognitive overhead remains
- No composability for context providers
- Inconsistent with middleware pattern used elsewhere

### Option 2: ContextMiddleware (Chosen)

Create a unified `ContextMiddleware` that uses the onion/wrapper pattern (like existing `AgentMiddleware`, `ChatMiddleware`) to handle all context-related concerns.

**Pros:**
- Single concept for all context engineering
- Familiar pattern from other middleware in the framework
- Natural composition via pipeline
- Pre/post processing in one method
- Source attribution built-in

**Cons:**
- Breaking change (acceptable in preview)
- Migration effort for existing users

## Decision Outcome

Chosen option: **"Option 2: ContextMiddleware"**, because it significantly reduces cognitive overhead, follows established patterns in the framework, and enables powerful composition for context engineering scenarios.

### Key Design Decisions

#### 1. Onion/Wrapper Pattern

Like other middleware in the framework, `ContextMiddleware` uses `process(context, next)`:

```python
class ContextMiddleware(ABC):
    def __init__(self, source_id: str, *, session_id: str | None = None):
        self.source_id = source_id
        self.session_id = session_id

    @abstractmethod
    async def process(self, context: SessionContext, next: ContextMiddlewareNext) -> None:
        """Wrap the context flow - modify before next(), process after."""
        pass
```

**Comparison to Current:**
| Aspect | ContextProvider (Current) | ContextMiddleware (New) |
|--------|--------------------------|------------------------|
| Pre-processing | `invoking()` method | Before `await next(context)` |
| Post-processing | `invoked()` method | After `await next(context)` |
| Composition | Single provider only | Pipeline of middleware |
| Pattern | Callback hooks | Onion/wrapper |

#### 2. Agent vs Session Ownership

- **Agent** owns `Sequence[ContextMiddlewareConfig]` (instances or factories)
- **AgentSession** owns `ContextMiddlewarePipeline` (resolved at runtime)

```python
# Agent holds middleware configuration
agent = ChatAgent(
    chat_client=client,
    context_middleware=[
        InMemoryStorageMiddleware("memory"),
        RAGContextMiddleware("rag"),
    ]
)

# Session holds the resolved pipeline
session = agent.get_new_session()
```

**Comparison to Current:**
| Aspect | AgentThread (Current) | AgentSession (New) |
|--------|----------------------|-------------------|
| Storage | `message_store` attribute | Via `StorageContextMiddleware` in pipeline |
| Context | `context_provider` attribute | Via any `ContextMiddleware` in pipeline |
| Composition | One of each | Unlimited middleware |

#### 3. Unified Storage Middleware

Instead of separate `ChatMessageStore`, storage is a type of `ContextMiddleware`:

```python
class StorageContextMiddleware(ContextMiddleware):
    def __init__(
        self,
        source_id: str,
        *,
        load_messages: bool | None = None,  # None = smart mode
        store_inputs: bool = True,
        store_responses: bool = True,
        store_context_messages: bool = False,
        store_context_from: Sequence[str] | None = None,
    ): ...
```

**Smart Load Behavior:**
- `load_messages=None` (default): Automatically disable loading when:
  - `context.options.get('store') == False`, OR
  - `context.service_session_id is not None` (service handles storage)

**Comparison to Current:**
| Aspect | ChatMessageStore (Current) | StorageContextMiddleware (New) |
|--------|---------------------------|------------------------------|
| Load messages | Always via `list_messages()` | Configurable `load_messages` flag |
| Store messages | Always via `add_messages()` | Configurable `store_*` flags |
| What to store | All messages | Selective: inputs, responses, context |
| RAG context | Not supported | `store_context_messages=True` |

#### 4. Source Attribution via `source_id`

Every middleware has a required `source_id` that attributes added messages:

```python
class SessionContext:
    # Messages keyed by source_id
    context_messages: dict[str, list[ChatMessage]]

    def add_messages(self, source_id: str, messages: Sequence[ChatMessage]) -> None:
        if source_id not in self.context_messages:
            self.context_messages[source_id] = []
        self.context_messages[source_id].extend(messages)

    def get_messages(
        self,
        sources: Sequence[str] | None = None,
        exclude_sources: Sequence[str] | None = None,
    ) -> list[ChatMessage]:
        """Get messages, optionally filtered by source."""
        ...
```

**Benefits over Current:**
- Debug which middleware added which messages
- Filter messages by source (e.g., exclude RAG from storage)
- Multiple instances of same middleware type distinguishable

#### 5. Default Storage Behavior

Zero-config works out of the box:

```python
# No middleware configured - still gets conversation history!
agent = ChatAgent(chat_client=client, name="assistant")
session = agent.get_new_session()
response = await agent.run("Hello!", session=session)
response = await agent.run("What did I say?", session=session)  # Remembers!
```

Default `InMemoryStorageMiddleware` is added at runtime when:
- No `service_session_id` (service not managing storage)
- `options.store` is not `True` (user not expecting service storage)
- Pipeline is empty or None

**Comparison to Current:**
| Aspect | AgentThread (Current) | AgentSession (New) |
|--------|----------------------|-------------------|
| Default storage | Creates `ChatMessageStore` lazily | Creates `InMemoryStorageMiddleware` at runtime |
| When | In `on_new_messages()` | In `run_context_pipeline()` |
| Customizable | After creation | Before first `run()` |

#### 6. Middleware Instance vs Factory

Support both shared instances and per-session factories:

```python
# Instance (shared across sessions)
agent = ChatAgent(
    context_middleware=[RAGContextMiddleware("rag")]
)

# Factory (new instance per session)
def create_session_cache(session_id: str | None) -> ContextMiddleware:
    return SessionCacheMiddleware("cache", session_id=session_id)

agent = ChatAgent(
    context_middleware=[create_session_cache]
)
```

#### 7. Renaming: Thread → Session

`AgentThread` becomes `AgentSession` to better reflect its purpose:
- "Thread" implies a sequence of messages
- "Session" better captures the broader scope (state, middleware, lifecycle)

### Migration Impact

| Current | New | Notes |
|---------|-----|-------|
| `ContextProvider` | `ContextMiddleware` | Implement `process()` instead of `invoking()`/`invoked()` |
| `ChatMessageStore` | `StorageContextMiddleware` | Extend and implement `get_messages()`/`save_messages()` |
| `AgentThread` | `AgentSession` | Clean break, no alias |
| `thread.message_store` | Via middleware in pipeline | Configure at agent level |
| `thread.context_provider` | Via middleware in pipeline | Multiple providers supported |

### Example: Current vs New

**Current:**
```python
class MyContextProvider(ContextProvider):
    async def invoking(self, messages, **kwargs) -> Context:
        docs = await self.retrieve_documents(messages[-1].text)
        return Context(messages=[ChatMessage.system(f"Context: {docs}")])

    async def invoked(self, request, response, **kwargs) -> None:
        await self.store_interaction(request, response)

async with MyContextProvider() as provider:
    agent = ChatAgent(chat_client=client, name="assistant")
    thread = await agent.get_new_thread(message_store=ChatMessageStore())
    thread.context_provider = provider
    response = await agent.run("Hello", thread=thread)
```

**New:**
```python
class RAGMiddleware(ContextMiddleware):
    async def process(self, context: SessionContext, next) -> None:
        # Pre-processing
        docs = await self.retrieve_documents(context.input_messages[-1].text)
        context.add_messages(self.source_id, [ChatMessage.system(f"Context: {docs}")])

        await next(context)

        # Post-processing
        await self.store_interaction(context.input_messages, context.response_messages)

agent = ChatAgent(
    chat_client=client,
    name="assistant",
    context_middleware=[
        InMemoryStorageMiddleware("memory"),
        RAGMiddleware("rag"),
    ]
)
session = agent.get_new_session()
response = await agent.run("Hello", session=session)
```

## Implementation Plan

See **Appendix A** for the detailed implementation plan including:
- Complete class definitions
- User experience examples
- Phase-by-phase workplan

---

## Appendix A: Implementation Plan

### New Types

```python
# Copyright (c) Microsoft. All rights reserved.

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from ._types import ChatMessage
from ._tools import ToolProtocol


class SessionContext:
    """State passed through the ContextMiddleware pipeline for a single invocation.

    This object is created fresh for each agent invocation and flows through the
    middleware pipeline. Middleware can read from and write to the mutable fields
    to add context before invocation and process responses after.

    Attributes:
        session_id: The ID of the current session
        service_session_id: Service-managed session ID (if present, service handles storage)
        input_messages: The new messages being sent to the agent (read-only, set by caller)
        context_messages: Dict mapping source_id -> messages added by that middleware.
            Maintains insertion order (middleware execution order). Use add_context_messages()
            to add messages with proper source attribution.
        instructions: Additional instructions - middleware can append here
        tools: Additional tools - middleware can append here
        response_messages: After invocation, contains the agent's response (set by agent)
        options: Options passed to agent.run() - READ-ONLY, for reflection only
        metadata: Shared metadata dictionary for cross-middleware communication

    Note:
        - `options` is read-only; changes will NOT be merged back into the agent run
        - `instructions` and `tools` are merged by the agent into the run options
        - `context_messages` values are flattened in order when building the final input
    """

    def __init__(
        self,
        *,
        session_id: str | None = None,
        service_session_id: str | None = None,
        input_messages: list[ChatMessage],
        context_messages: dict[str, list[ChatMessage]] | None = None,
        instructions: list[str] | None = None,
        tools: list[ToolProtocol] | None = None,
        response_messages: list[ChatMessage] | None = None,
        options: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.session_id = session_id
        self.service_session_id = service_session_id
        self.input_messages = input_messages
        self.context_messages: dict[str, list[ChatMessage]] = context_messages or {}
        self.instructions: list[str] = instructions or []
        self.tools: list[ToolProtocol] = tools or []
        self.response_messages = response_messages
        self.options = options or {}  # READ-ONLY - for reflection only
        self.metadata = metadata or {}

    # --- Methods for adding context ---

    def add_messages(self, source_id: str, messages: Sequence[ChatMessage]) -> None:
        """Add context messages from a specific source.

        Messages are stored keyed by source_id, maintaining insertion order
        based on middleware execution order.

        Args:
            source_id: The middleware source_id adding these messages
            messages: The messages to add
        """
        if source_id not in self.context_messages:
            self.context_messages[source_id] = []
        self.context_messages[source_id].extend(messages)

    def add_instructions(self, source_id: str, instructions: str | Sequence[str]) -> None:
        """Add instructions to be prepended to the conversation.

        Instructions are added to a flat list. The source_id is recorded
        in metadata for debugging but instructions are not keyed by source.

        Args:
            source_id: The middleware source_id adding these instructions
            instructions: A single instruction string or sequence of strings
        """
        if isinstance(instructions, str):
            instructions = [instructions]
        self.instructions.extend(instructions)

    def add_tools(self, source_id: str, tools: Sequence[ToolProtocol]) -> None:
        """Add tools to be available for this invocation.

        Tools are added with source attribution in their metadata.

        Args:
            source_id: The middleware source_id adding these tools
            tools: The tools to add
        """
        for tool in tools:
            # Add source attribution to tool metadata
            if hasattr(tool, 'metadata') and isinstance(tool.metadata, dict):
                tool.metadata["context_source"] = source_id
        self.tools.extend(tools)

    # --- Methods for reading context ---

    def get_messages(
        self,
        sources: Sequence[str] | None = None,
        exclude_sources: Sequence[str] | None = None,
    ) -> list[ChatMessage]:
        """Get context messages, optionally filtered by source.

        Returns messages in middleware execution order (dict insertion order).

        Args:
            sources: If provided, only include messages from these sources
            exclude_sources: If provided, exclude messages from these sources

        Returns:
            Flattened list of messages in middleware execution order
        """
        result: list[ChatMessage] = []
        for source_id, messages in self.context_messages.items():
            if sources is not None and source_id not in sources:
                continue
            if exclude_sources is not None and source_id in exclude_sources:
                continue
            result.extend(messages)
        return result

    def get_all_messages(
        self,
        *,
        include_input: bool = False,
        include_response: bool = False,
    ) -> list[ChatMessage]:
        """Get all messages, optionally including input and response.

        Returns messages in the order they would appear in a full conversation:
        1. Context messages (from middleware, in execution order)
        2. Input messages (if include_input=True)
        3. Response messages (if include_response=True)

        Args:
            include_input: If True, append input_messages after context
            include_response: If True, append response_messages at the end

        Returns:
            Flattened list of messages in conversation order
        """
        result: list[ChatMessage] = []

        # Context messages in middleware execution order
        for messages in self.context_messages.values():
            result.extend(messages)

        # Input messages (user's new messages for this invocation)
        if include_input and self.input_messages:
            result.extend(self.input_messages)

        # Response messages (agent's response)
        if include_response and self.response_messages:
            result.extend(self.response_messages)

        return result


# Type alias for the next middleware callable
ContextMiddlewareNext = Callable[[SessionContext], Awaitable[None]]

# Type alias for middleware factory - takes session_id, returns middleware
ContextMiddlewareFactory = Callable[[str | None], ContextMiddleware]

# Union type for middleware configuration - either instance or factory
ContextMiddlewareConfig = ContextMiddleware | ContextMiddlewareFactory


class ContextMiddleware(ABC):
    """Base class for context middleware (onion/wrapper pattern).

    Context middleware wraps the context preparation and storage flow,
    allowing modification of messages, tools, and instructions before
    invocation and processing of responses after invocation.

    The process() method receives a context and a next() callable.
    Before calling next(), you can modify the context (add messages, tools, etc.).
    After calling next(), the response_messages will be populated and you can
    process them (store, extract info, etc.).

    Lifecycle:
    - session_created(): Called once when a new session is created
    - process(): Called for each invocation, wraps the context flow

    Attributes:
        source_id: Unique identifier for this middleware instance (required).
            Used for message/tool attribution so other middleware can filter.
        session_id: The session ID, automatically set when created via factory.
            None if middleware is shared across sessions (instance mode).

    Note:
        Middleware can be provided to agents as either:
        - An instantiated middleware object (shared across all sessions)
        - A factory function `(session_id: str | None) -> ContextMiddleware`
          that creates a new instance per session

    Examples:
        # As instance (shared across sessions)
        class MyContextMiddleware(ContextMiddleware):
            def __init__(self, source_id: str):
                super().__init__(source_id=source_id)

            async def process(self, context, next):
                context.add_instructions(self.source_id, "Be helpful!")
                await next(context)

        # As factory (new instance per session)
        def create_session_middleware(session_id: str | None) -> ContextMiddleware:
            return MySessionMiddleware(
                source_id="session_specific",
                session_id=session_id,
            )

                # POST-PROCESSING: Handle response after invocation
                for msg in context.response_messages or []:
                    print(f"Response: {msg.text}")
    """

    def __init__(self, source_id: str, *, session_id: str | None = None):
        """Initialize the middleware.

        Args:
            source_id: Unique identifier for this middleware instance.
                Used for message/tool attribution.
            session_id: Optional session ID. Automatically set when middleware
                is created via a factory function.
        """
        self.source_id = source_id
        self.session_id = session_id

    async def session_created(self, session_id: str | None) -> None:
        """Called when a new session is created.

        Override this to load any initial data from persistent storage
        or perform session-level initialization.

        Note: If you need the session_id, prefer using `self.session_id`
        which is set automatically when using a factory.

        Args:
            session_id: The ID of the newly created session
        """
        pass

    @abstractmethod
    async def process(
        self,
        context: SessionContext,
        next: ContextMiddlewareNext
    ) -> None:
        """Process the context, wrapping the call to next middleware.

        Before calling next():
        - Modify context.context_messages to add messages (RAG, memory, etc.)
        - Modify context.instructions to add system instructions
        - Modify context.tools to add tools for this invocation
        - Access context.history_messages to see loaded history
        - Access context.input_messages to see new user messages

        After calling next():
        - context.response_messages contains the agent's response
        - Store messages, extract information, perform cleanup

        Args:
            context: The invocation context being processed
            next: Callable to invoke the next middleware in the chain
        """
        pass
```

### Storage Middleware Base

```python
class StorageContextMiddleware(ContextMiddleware):
    """Base class for storage-focused context middleware.

    A single class that can be configured for different use cases:
    - Primary memory storage (loads + stores messages)
    - Audit/logging storage (stores only, doesn't load)
    - Evaluation storage (stores only for later analysis)

    Loading behavior (when to add messages to context_messages[source_id]):
    - `load_messages=True`: Always load messages
    - `load_messages=False`: Never load (audit/logging mode)
    - `load_messages=None` (default): Smart mode - load unless:
      - `context.options.get('store', True)` is False, OR
      - `context.service_session_id` is present (service manages storage)

    Storage behavior:
    - `store_inputs`: Store input messages (default True)
    - `store_responses`: Store response messages (default True)
    - Storage always happens unless explicitly disabled, regardless of load_messages

    Warning: If multiple middleware have load_messages=True, a warning
    is logged at pipeline creation time (likely misconfiguration).

    Examples:
        # Primary memory - loads and stores
        memory = InMemoryStorageMiddleware(source_id="memory")

        # Audit storage - stores only, doesn't add to context
        audit = RedisStorageMiddleware(
            source_id="audit",
            load_messages=False,
            redis_url="redis://...",
        )

        # Evaluation storage - stores responses only
        eval_storage = CosmosStorageMiddleware(
            source_id="evaluation",
            load_messages=False,
            store_inputs=False,
            store_responses=True,
        )

        # Full audit - stores everything including RAG context
        full_audit = CosmosStorageMiddleware(
            source_id="full_audit",
            load_messages=False,
            store_context_messages=True,  # Also store context from other middleware
        )
    """

    def __init__(
        self,
        source_id: str,
        *,
        session_id: str | None = None,
        load_messages: bool | None = None,  # None = smart mode
        store_responses: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,  # Store context added by other middleware
        store_context_from: Sequence[str] | None = None,  # Only store from these sources
    ):
        super().__init__(source_id, session_id=session_id)
        self.load_messages = load_messages
        self.store_responses = store_responses
        self.store_inputs = store_inputs
        self.store_context_messages = store_context_messages
        self.store_context_from = list(store_context_from) if store_context_from else None

    @abstractmethod
    async def get_messages(self, session_id: str | None) -> list[ChatMessage]:
        """Retrieve stored messages for this session."""
        pass

    @abstractmethod
    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[ChatMessage]
    ) -> None:
        """Persist messages for this session."""
        pass

    def _should_load_messages(self, context: SessionContext) -> bool:
        """Determine if we should load messages based on config and context."""
        # Explicit configuration takes precedence
        if self.load_messages is not None:
            return self.load_messages

        # Smart mode: don't load if service manages storage
        if context.service_session_id is not None:
            return False

        # Smart mode: respect options['store']
        return context.options.get('store', True)

    def _get_context_messages_to_store(self, context: SessionContext) -> list[ChatMessage]:
        """Get context messages that should be stored based on configuration."""
        if not self.store_context_messages:
            return []

        if self.store_context_from is not None:
            # Only store from specific sources
            return context.get_messages(sources=self.store_context_from)
        else:
            # Store all context messages (excluding our own to avoid duplication)
            return context.get_messages(exclude_sources=[self.source_id])

    async def process(
        self,
        context: SessionContext,
        next: ContextMiddlewareNext
    ) -> None:
        # PRE: Load history if configured, keyed by our source_id
        if self._should_load_messages(context):
            history = await self.get_messages(context.session_id)
            context.add_messages(self.source_id, history)

        # Continue to next middleware
        await next(context)

        # POST: Store messages
        messages_to_store: list[ChatMessage] = []

        # Optionally store context messages from other middleware
        messages_to_store.extend(self._get_context_messages_to_store(context))

        if self.store_inputs:
            messages_to_store.extend(context.input_messages)
        if self.store_responses and context.response_messages:
            messages_to_store.extend(context.response_messages)
        if messages_to_store:
            await self.save_messages(context.session_id, messages_to_store)
```

### Message/Tool Attribution

The `SessionContext` provides explicit methods for adding context:

```python
# Adding messages (keyed by source_id in context_messages dict)
context.add_messages(self.source_id, messages)

# Adding instructions (flat list, source_id for debugging)
context.add_instructions(self.source_id, "Be concise and helpful.")
context.add_instructions(self.source_id, ["Instruction 1", "Instruction 2"])

# Adding tools (source attribution added to tool.metadata automatically)
context.add_tools(self.source_id, [my_tool, another_tool])

# Getting all messages in middleware execution order
all_messages = context.get_all_messages()

# Filtering by source
memory_messages = context.get_messages(sources=["memory"])
non_rag_messages = context.get_messages(exclude_sources=["rag"])

# Direct access to check specific sources
if "memory" in context.context_messages:
    history = context.context_messages["memory"]
```

### AgentSession Class (replaces AgentThread)

```python
import uuid
import warnings
from collections.abc import Sequence


def _resolve_middleware(
    config: ContextMiddlewareConfig,
    session_id: str | None,
) -> ContextMiddleware:
    """Resolve a middleware config to an instance.

    If config is already a ContextMiddleware instance, return it.
    If config is a factory callable, call it with session_id to create an instance.
    """
    if isinstance(config, ContextMiddleware):
        return config
    # It's a factory - call it with session_id
    return config(session_id)


class ContextMiddlewarePipeline:
    """Executes a chain of context middleware in onion/wrapper style."""

    def __init__(self, middleware: Sequence[ContextMiddleware]):
        self._middleware = list(middleware)
        self._validate_middleware()

    @classmethod
    def from_config(
        cls,
        configs: Sequence[ContextMiddlewareConfig],
        session_id: str | None,
    ) -> "ContextMiddlewarePipeline":
        """Create a pipeline from middleware configs, resolving factories.

        Args:
            configs: Sequence of middleware instances or factories
            session_id: Session ID to pass to factories

        Returns:
            A new pipeline with resolved middleware instances
        """
        middleware = [_resolve_middleware(config, session_id) for config in configs]
        return cls(middleware)

    def _validate_middleware(self) -> None:
        """Warn if multiple middleware are configured to load messages."""
        loaders = [
            m for m in self._middleware
            if isinstance(m, StorageContextMiddleware)
            and m.load_messages is True
        ]
        if len(loaders) > 1:
            warnings.warn(
                f"Multiple storage middleware configured to load messages: "
                f"{[m.source_id for m in loaders]}. "
                f"This may cause duplicate messages in context. "
                f"Consider setting load_messages=False on all but one.",
                UserWarning
            )

    async def session_created(self, session_id: str | None) -> None:
        """Notify all middleware that a session was created."""
        for middleware in self._middleware:
            await middleware.session_created(session_id)

    async def execute(self, context: SessionContext) -> None:
        """Execute the middleware pipeline."""

        async def terminal(s: SessionContext) -> None:
            # Terminal handler - nothing more to do
            pass

        # Build the chain from last to first
        next_handler = terminal
        for middleware in reversed(self._middleware):
            # Capture middleware in closure
            current_middleware = middleware
            current_next = next_handler

            async def handler(s: SessionContext, mw=current_middleware, nxt=current_next) -> None:
                await mw.process(s, nxt)

            next_handler = handler

        # Execute the chain
        await next_handler(context)


class AgentSession:
    """A conversation session with an agent.

    AgentSession manages the conversation state and owns a ContextMiddlewarePipeline
    that processes context before each invocation and handles responses after.

    Note: The session is created by calling agent.get_new_session(), which constructs
    the pipeline from the agent's context_middleware sequence, resolving any factories.

    Attributes:
        session_id: Unique identifier for this session
        service_session_id: Service-managed session ID (if using service-side storage)
        context_pipeline: The middleware pipeline for this session
    """

    def __init__(
        self,
        *,
        session_id: str | None = None,
        service_session_id: str | None = None,
        context_pipeline: ContextMiddlewarePipeline | None = None,
    ):
        """Initialize the session.

        Note: Prefer using agent.get_new_session() instead of direct construction.

        Default storage behavior (applied at runtime, not init):
        - If service_session_id is set: service handles storage, no default added
        - If options.store=True: user expects service storage, no default added
        - If no service_session_id AND store is not True AND no pipeline:
          InMemoryStorageMiddleware is automatically added

        Args:
            session_id: Optional session ID (generated if not provided)
            service_session_id: Optional service-managed session ID
            context_pipeline: The middleware pipeline (created by agent)
        """
        self._session_id = session_id or str(uuid.uuid4())
        self._service_session_id = service_session_id
        self._context_pipeline = context_pipeline
        self._initialized = False
        self._default_storage_checked = False

    @property
    def session_id(self) -> str:
        """The unique identifier for this session."""
        return self._session_id

    @property
    def service_session_id(self) -> str | None:
        """The service-managed session ID (if using service-side storage)."""
        return self._service_session_id

    @service_session_id.setter
    def service_session_id(self, value: str | None) -> None:
        self._service_session_id = value

    @property
    def context_pipeline(self) -> ContextMiddlewarePipeline | None:
        """The middleware pipeline for this session."""
        return self._context_pipeline

    @context_pipeline.setter
    def context_pipeline(self, value: ContextMiddlewarePipeline | None) -> None:
        """Set the middleware pipeline for this session."""
        self._context_pipeline = value

    def _ensure_default_storage(self, options: dict[str, Any]) -> None:
        """Add default InMemoryStorageMiddleware if needed.

        Called at runtime (first run) so users can modify the pipeline
        after session creation but before first invocation.

        Default storage is added when ALL of these are true:
        - No service_session_id (service not managing storage)
        - options.store is not True (user not expecting service storage)
        - Pipeline is empty or None (user hasn't configured middleware)
        """
        if self._default_storage_checked:
            return
        self._default_storage_checked = True

        # User expects service-side storage
        if options.get("store") is True:
            return

        # Service is managing storage
        if self._service_session_id is not None:
            return

        # User has configured middleware
        if self._context_pipeline is not None and len(self._context_pipeline) > 0:
            return

        # Add default in-memory storage
        default_middleware = InMemoryStorageMiddleware("memory")
        if self._context_pipeline is None:
            self._context_pipeline = ContextMiddlewarePipeline([default_middleware])
        else:
            self._context_pipeline.prepend(default_middleware)

    async def initialize(self) -> None:
        """Initialize the session and notify middleware."""
        if not self._initialized and self._context_pipeline is not None:
            await self._context_pipeline.session_created(self._session_id)
            self._initialized = True

    async def run_context_pipeline(
        self,
        input_messages: list[ChatMessage],
        *,
        tools: list[ToolProtocol] | None = None,
        options: dict[str, Any] | None = None,
    ) -> SessionContext:
        """Prepare context by running the middleware pipeline.

        This runs the full middleware pipeline (pre-processing, then post-processing
        after response_messages is set).

        Args:
            input_messages: New messages to send to the agent
            tools: Additional tools available for this invocation
            options: Options including 'store' flag (READ-ONLY, for reflection)

        Returns:
            The invocation context with history, context, instructions, and tools populated
        """
        options = options or {}

        # Check for default storage on first run (deferred from init)
        self._ensure_default_storage(options)

        await self.initialize()
        context = SessionContext(
            session_id=self._session_id,
            service_session_id=self._service_session_id,
            input_messages=input_messages,
            tools=tools or [],
            options=options,
        )
        if self._context_pipeline is not None:
            await self._context_pipeline.execute(context)
        return context


# Example of how agent creates sessions:
class ChatAgent:
    def __init__(
        self,
        chat_client: ...,
        *,
        context_middleware: Sequence[ContextMiddleware] | None = None,
        # ... other params
    ):
        self._context_middleware = list(context_middleware or [])
        # ... other init

    def get_new_session(
        self,
        *,
        session_id: str | None = None,
        service_session_id: str | None = None,
    ) -> AgentSession:
        """Create a new session with a fresh middleware pipeline.

        Middleware factories are called with the session_id to create
        session-specific instances.

        Args:
            session_id: Optional session ID (generated if not provided)
            service_session_id: Optional service-managed session ID
        """
        resolved_session_id = session_id or str(uuid.uuid4())

        # Only create pipeline if we have middleware configured
        pipeline = None
        if self._context_middleware:
            pipeline = ContextMiddlewarePipeline.from_config(
                self._context_middleware,
                session_id=resolved_session_id,
            )

        return AgentSession(
            session_id=resolved_session_id,
            service_session_id=service_session_id,
            context_pipeline=pipeline,
        )

    async def run(self, input: str, *, session: AgentSession, options: dict[str, Any] | None = None) -> ...:
        """Run the agent with the given input."""
        # Default storage check happens inside session.run_context_pipeline()
        # ... rest of run logic
```

---

## User Experience Examples

### Example 0: Zero-Config Default (Simplest Use Case)

```python
from agent_framework import ChatAgent

# No middleware configured - but conversation history still works!
agent = ChatAgent(
    chat_client=client,
    name="assistant",
    # No context_middleware specified
)

# Create session - automatically gets InMemoryStorageMiddleware on first run
session = agent.get_new_session()
response = await agent.run("Hello, my name is Alice!", session=session)

# Conversation history is preserved automatically
response = await agent.run("What's my name?", session=session)
# Agent remembers: "Your name is Alice!"

# With service-managed session - no default storage added (service handles it)
service_session = agent.get_new_session()

# With store=True in options - user expects service storage, no default added
response = await agent.run("Hello!", session=session, options={"store": True})

# User can manually add middleware to session before first run
session = agent.get_new_session()
session.context_pipeline = ContextMiddlewarePipeline([
    MyCustomMiddleware(source_id="custom")
])
response = await agent.run("Hello!", session=session)  # No default added since pipeline exists
```

### Example 1: Explicit Memory Storage

```python
from agent_framework import ChatAgent
from agent_framework.context import InMemoryStorageMiddleware

# Explicit middleware configuration (same behavior as default, but explicit)
agent = ChatAgent(
    chat_client=client,
    name="assistant",
    context_middleware=[
        InMemoryStorageMiddleware(source_id="memory")
    ]
)

# Create session and chat
session = agent.get_new_session()
response = await agent.run("Hello!", session=session)

# Messages are automatically stored and loaded on next invocation
response = await agent.run("What did I say before?", session=session)
```

### Example 1b: Using Middleware Factory for Per-Session State

```python
from agent_framework import ChatAgent
from agent_framework.context import ContextMiddleware, SessionContext

class SessionSpecificMiddleware(ContextMiddleware):
    """Middleware that stores state per session."""

    def __init__(self, source_id: str, session_id: str | None):
        super().__init__(source_id=source_id)
        self.session_id = session_id
        self.invocation_count = 0  # Per-session counter

    async def process(self, context: SessionContext, next) -> None:
        self.invocation_count += 1
        context.add_instructions(
            self.source_id,
            f"This is invocation #{self.invocation_count} in session {self.session_id}"
        )
        await next(context)


# Factory function - receives session_id when session is created
def create_session_middleware(session_id: str | None) -> ContextMiddleware:
    return SessionSpecificMiddleware(
        source_id="session_tracker",
        session_id=session_id,
    )


# Agent with factory - each session gets its own middleware instance
agent = ChatAgent(
    chat_client=client,
    name="assistant",
    context_middleware=[
        InMemoryStorageMiddleware(source_id="memory"),  # Instance (shared)
        create_session_middleware,  # Factory (per-session)
    ]
)

# Each session gets a fresh SessionSpecificMiddleware instance
session1 = agent.get_new_session()
session2 = agent.get_new_session()
# session1 and session2 have independent invocation_count
```

### Example 2: RAG + Memory + Audit (All StorageContextMiddleware)

```python
from agent_framework import ChatAgent
from agent_framework.azure import CosmosStorageMiddleware, AzureAISearchContextMiddleware
from agent_framework.redis import RedisStorageMiddleware

# RAG middleware that injects relevant documents
search_middleware = AzureAISearchContextMiddleware(
    source_id="rag",
    endpoint="https://...",
    index_name="documents",
)

# Primary memory storage (loads + stores)
# load_messages=None (default) = smart mode, respects options['store'] and service_session_id
memory_middleware = RedisStorageMiddleware(
    source_id="memory",
    redis_url="redis://...",
)

# Audit storage - SAME CLASS, different configuration
# load_messages=False = never loads, just stores for audit
audit_middleware = CosmosStorageMiddleware(
    source_id="audit",
    connection_string="...",
    load_messages=False,  # Don't load - just store for audit
)

agent = ChatAgent(
    chat_client=client,
    name="assistant",
    context_middleware=[
        memory_middleware,   # First: loads history (smart mode)
        search_middleware,   # Second: adds RAG context
        audit_middleware,    # Third: stores for audit (no load)
    ]
)
```

### Example 3: Custom Context Middleware (Onion Pattern)

```python
from agent_framework.context import ContextMiddleware, SessionContext

class TimeContextMiddleware(ContextMiddleware):
    """Adds current time to the context."""

    def __init__(self, source_id: str):
        super().__init__(source_id=source_id)

    async def process(
        self,
        context: SessionContext,
        next
    ) -> None:
        from datetime import datetime

        # PRE: Add time instruction using explicit method
        context.add_instructions(
            self.source_id,
            f"Current date and time: {datetime.now().isoformat()}"
        )

        # Continue to next middleware
        await next(context)

        # POST: Nothing to do after invocation for this middleware


class UserPreferencesMiddleware(ContextMiddleware):
    """Tracks and applies user preferences from conversation."""

    def __init__(self, source_id: str):
        super().__init__(source_id=source_id)
        self._preferences: dict[str, dict[str, Any]] = {}

    async def process(
        self,
        context: SessionContext,
        next
    ) -> None:
        # PRE: Add known preferences as instructions
        prefs = self._preferences.get(context.session_id or "", {})
        if prefs:
            context.add_instructions(
                self.source_id,
                f"User preferences: {json.dumps(prefs)}"
            )

        # Continue to next middleware and model invocation
        await next(context)

        # POST: Extract preferences from response
        for msg in context.response_messages or []:
            if "preference:" in msg.text.lower():
                # Store extracted preference for future sessions
                pass


# Compose middleware - each with mandatory source_id
agent = ChatAgent(
    chat_client=client,
    context_middleware=[
        InMemoryStorageMiddleware(source_id="memory"),
        TimeContextMiddleware(source_id="time"),
        UserPreferencesMiddleware(source_id="prefs"),
    ]
)
```

### Example 4: Filtering by Source (Using Dict-Based Context)

```python
class SelectiveContextMiddleware(ContextMiddleware):
    """Middleware that only processes messages from specific sources."""

    def __init__(self, source_id: str):
        super().__init__(source_id=source_id)

    async def process(
        self,
        context: SessionContext,
        next
    ) -> None:
        # Check what sources have added messages so far
        print(f"Sources so far: {list(context.context_messages.keys())}")

        # Get messages excluding RAG context
        non_rag_messages = context.get_messages(exclude_sources=["rag"])

        # Or get only memory messages
        if "memory" in context.context_messages:
            memory_only = context.context_messages["memory"]

        # Do something with filtered messages...
        # e.g., sentiment analysis, topic extraction

        # Continue to next middleware
        await next(context)


class RAGContextMiddleware(ContextMiddleware):
    """Middleware that adds RAG context."""

    def __init__(self, source_id: str):
        super().__init__(source_id=source_id)

    async def process(
        self,
        context: SessionContext,
        next
    ) -> None:
        # Search for relevant documents based on input
        relevant_docs = await self._search(context.input_messages)

        # Add RAG context using explicit method
        rag_messages = [
            ChatMessage(role="system", text=f"Relevant info: {doc}")
            for doc in relevant_docs
        ]
        context.add_messages(self.source_id, rag_messages)

        await next(context)
```

### Example 5: Smart Storage with options.store and service_session_id

```python
# Default StorageContextMiddleware already has smart behavior!
# load_messages=None (default) means:
#   - Don't load if options['store'] is False
#   - Don't load if service_session_id is present (service manages storage)
#   - Otherwise, load messages

agent = ChatAgent(
    chat_client=client,
    context_middleware=[
        RedisStorageMiddleware(
            source_id="memory",
            redis_url="redis://...",
            # load_messages=None is the default - smart mode
        )
    ]
)

session = agent.get_new_session()

# Normal run - loads and stores messages
response = await agent.run("Hello!", session=session)

# Run without loading history (but still stores for audit)
response = await agent.run(
    "What's 2+2?",
    session=session,
    options={"store": False}  # Don't load history for this call
)

# With service-managed session - won't load (service handles it)
service_session = agent.get_new_session(service_session_id="thread_abc123")
response = await agent.run("Hello!", session=service_session)
# Storage middleware sees service_session_id, skips loading
```

### Example 6: Multiple Instances of Same Middleware Type

```python
# You can have multiple instances of the same middleware class
# by using different source_ids

agent = ChatAgent(
    chat_client=client,
    context_middleware=[
        # Primary storage for conversation history
        RedisStorageMiddleware(
            source_id="conversation_memory",
            redis_url="redis://primary...",
            load_messages=True,  # This one loads
        ),
        # Secondary storage for audit (different Redis instance)
        RedisStorageMiddleware(
            source_id="audit_log",
            redis_url="redis://audit...",
            load_messages=False,  # This one just stores
        ),
    ]
)
# Warning will NOT be logged because only one has load_messages=True
```

### Example 7: Middleware Ordering - RAG Before vs After Memory

The order of middleware determines what context each middleware can see. This is especially important for RAG, which may benefit from seeing conversation history.

```python
from agent_framework import ChatAgent
from agent_framework.context import InMemoryStorageMiddleware, ContextMiddleware, SessionContext

class RAGContextMiddleware(ContextMiddleware):
    """RAG middleware that retrieves relevant documents based on available context."""

    async def process(self, context: SessionContext, next) -> None:
        # Build query from what we can see
        query_parts = []

        # We can always see the current input
        for msg in context.input_messages:
            query_parts.append(msg.text)

        # Can we see history? Depends on middleware order!
        history = context.get_all_messages()  # Gets context from middleware that ran before us
        if history:
            # Include recent history for better RAG context
            recent = history[-3:]  # Last 3 messages
            for msg in recent:
                query_parts.append(msg.text)

        query = " ".join(query_parts)
        documents = await self._retrieve_documents(query)

        # Add retrieved documents as context
        rag_messages = [ChatMessage.system(f"Relevant context:\n{doc}") for doc in documents]
        context.add_messages(self.source_id, rag_messages)

        await next(context)

    async def _retrieve_documents(self, query: str) -> list[str]:
        # ... vector search implementation
        return ["doc1", "doc2"]


# =============================================================================
# SCENARIO A: RAG runs BEFORE Memory
# =============================================================================
# RAG only sees the current input message - no conversation history
# Use when: RAG should be based purely on the current query

agent_rag_first = ChatAgent(
    chat_client=client,
    context_middleware=[
        RAGContextMiddleware("rag"),           # Runs first - only sees input_messages
        InMemoryStorageMiddleware("memory"),   # Runs second - loads/stores history
    ]
)

# Flow:
# 1. RAG.process() BEFORE next():
#    - context.input_messages = ["What's the weather?"]
#    - context.get_all_messages() = []  (empty - memory hasn't run yet)
#    - RAG query based on: "What's the weather?" only
#    - Adds: context_messages["rag"] = [retrieved docs]
#
# 2. Memory.process() BEFORE next():
#    - context.get_all_messages() = [rag docs]  (sees RAG context)
#    - Loads history: context_messages["memory"] = [previous conversation]
#
# 3. Agent invocation with: history + rag docs + input
#
# 4. Memory.process() AFTER next():
#    - Stores: input + response (not RAG docs by default)


# =============================================================================
# SCENARIO B: RAG runs AFTER Memory
# =============================================================================
# RAG sees conversation history - can use it for better retrieval
# Use when: RAG should consider conversation context for better results

agent_memory_first = ChatAgent(
    chat_client=client,
    context_middleware=[
        InMemoryStorageMiddleware("memory"),   # Runs first - loads history
        RAGContextMiddleware("rag"),           # Runs second - sees history + input
    ]
)

# Flow:
# 1. Memory.process() BEFORE next():
#    - Loads history: context_messages["memory"] = [previous conversation]
#
# 2. RAG.process() BEFORE next():
#    - context.input_messages = ["What's the weather?"]
#    - context.get_all_messages() = [previous conversation]  (sees history!)
#    - RAG query based on: recent history + "What's the weather?"
#    - Better retrieval because RAG understands conversation context
#    - Adds: context_messages["rag"] = [more relevant docs]
#
# 3. Agent invocation with: history + rag docs + input
#
# 4. Memory.process() AFTER next():
#    - Stores: input + response


# =============================================================================
# SCENARIO C: RAG after Memory, with selective storage
# =============================================================================
# Memory first for better RAG, plus separate audit that stores RAG context

agent_full_context = ChatAgent(
    chat_client=client,
    context_middleware=[
        InMemoryStorageMiddleware("memory"),   # Primary history storage
        RAGContextMiddleware("rag"),           # Gets history context for better retrieval
        PersonaContextMiddleware("persona"),   # Adds persona instructions
        # Audit storage - stores everything including RAG results
        CosmosStorageMiddleware(
            "audit",
            load_messages=False,               # Don't load (memory handles that)
            store_context_messages=True,       # Store RAG + persona context too
        ),
    ]
)
```

### Example 8: Understanding the Onion Pattern for Storage

```python
# Detailed breakdown of what storage middleware sees at each phase:
#
# Middleware order: [Storage, RAG, Persona]
#
# BEFORE next() - Storage pre-processing:
#   context.context_messages = {}  (empty, no one has added yet)
#   context.input_messages = [user's message]
#   context.response_messages = None
#
# BEFORE next() - RAG pre-processing:
#   context.context_messages = {"memory": [...]}  (storage added history)
#
# BEFORE next() - Persona pre-processing:
#   context.context_messages = {"memory": [...], "rag": [...]}
#
# --- Agent invocation happens ---
#
# AFTER next() - Persona post-processing:
#   context.response_messages = [assistant's response]
#
# AFTER next() - RAG post-processing:
#   (same state)
#
# AFTER next() - Storage post-processing:
#   context.context_messages = {"memory": [...], "rag": [...], "persona": [...]}
#   context.response_messages = [assistant's response]
#
#   Storage NOW has access to ALL context if store_context_messages=True

class StorageWithLogging(StorageContextMiddleware):
    """Example showing what storage sees at each phase."""

    async def process(self, context: SessionContext, next) -> None:
        # PRE: Load history
        print(f"PRE - context sources: {list(context.context_messages.keys())}")
        # Output: PRE - context sources: []

        if self._should_load_messages(context):
            history = await self.get_messages(context.session_id)
            context.add_messages(self.source_id, history)

        await next(context)

        # POST: Now we see everything
        print(f"POST - context sources: {list(context.context_messages.keys())}")
        # Output: POST - context sources: ['memory', 'rag', 'persona']

        # Store based on configuration
        # 1. Determine which context messages to include
        if self.store_context_messages:
            if self.store_context_from:
                # Only from specific sources
                context_msgs = context.get_messages(sources=self.store_context_from)
            else:
                # All context messages from all middleware
                context_msgs = context.get_all_messages()
        else:
            # No context from other middleware - typically just our own loaded history
            context_msgs = []

        # 2. Build final list: context + input + response
        messages_to_store = list(context_msgs)
        if self.store_inputs:
            messages_to_store.extend(context.input_messages)
        if self.store_responses:
            messages_to_store.extend(context.response_messages or [])

        await self.save_messages(context.session_id, messages_to_store)
```

---

### Workplan

#### Phase 1: Core Implementation
- [ ] Create `ContextMiddleware` base class in `_context_middleware.py` (onion/wrapper pattern)
- [ ] Create `SessionContext` class with explicit add/get methods
- [ ] Create `ContextMiddlewarePipeline` with `from_config()` factory method
- [ ] Create `ContextMiddlewareFactory` type alias and resolution logic
- [ ] Create `StorageContextMiddleware` base class with load_messages/store flags
- [ ] Implement pipeline validation (warn on multiple loaders with `load_messages=True`)

#### Phase 2: AgentSession Implementation
- [ ] Create `AgentSession` class with `context_pipeline` attribute
- [ ] Add `context_middleware: Sequence[ContextMiddlewareConfig]` parameter to `BaseAgent` and `ChatAgent`
- [ ] Implement `get_new_session()` that resolves factories and creates pipeline
- [ ] Wire up context pipeline execution in agent invocation flow
- [ ] Remove `AgentThread` completely (no alias, clean break)

#### Phase 3: Built-in Middleware
- [ ] Create `InMemoryStorageMiddleware` (replaces `ChatMessageStore`)
- [ ] Create `@context_middleware` decorator for function-based middleware

#### Phase 4: Migrate Existing Implementations
- [ ] Migrate `AzureAISearchContextProvider` → `AzureAISearchContextMiddleware`
- [ ] Migrate `RedisProvider` → `RedisStorageMiddleware`
- [ ] Migrate `Mem0Provider` → `Mem0ContextMiddleware`
- [ ] Create optional `ContextProviderAdapter` for gradual migration (if needed)

#### Phase 5: Cleanup & Documentation
- [ ] Remove `ContextProvider` class
- [ ] Remove `ChatMessageStore` / `ChatMessageStoreProtocol`
- [ ] Update all samples to use new middleware pattern
- [ ] Write migration guide
- [ ] Update API documentation

#### Phase 6: Testing
- [ ] Unit tests for `ContextMiddleware` and pipeline execution order
- [ ] Unit tests for middleware factory resolution
- [ ] Unit tests for `StorageContextMiddleware` load/store behavior
- [ ] Unit tests for `options.store` and `service_session_id` triggers
- [ ] Unit tests for source attribution (mandatory source_id)
- [ ] Unit tests for `store_context_messages` and `store_context_from` options
- [ ] Integration tests for full agent flow with middleware
