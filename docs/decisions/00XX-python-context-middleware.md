---
# These are optional elements. Feel free to remove any of them.
status: accepted
contact: eavanvalkenburg
date: 2026-02-05
deciders: eavanvalkenburg, markwallace-microsoft, sphenry, alliscode, johanst, brettcannon, westey-m
consulted: taochenosu, moonbox3, dmytrostruk, giles17
---

# Unifying Context Management with ContextPlugin

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

## Related Issues

This ADR addresses the following issues from the parent issue [#3575](https://github.com/microsoft/agent-framework/issues/3575):

| Issue | Title | How Addressed |
|-------|-------|---------------|
| [#3587](https://github.com/microsoft/agent-framework/issues/3587) | Rename AgentThread to AgentSession | ✅ `AgentThread` → `AgentSession` (clean break, no alias). See [§7 Renaming](#7-renaming-thread--session). |
| [#3588](https://github.com/microsoft/agent-framework/issues/3588) | Add get_new_session, get_session_by_id methods | ✅ `agent.create_session()` (no params) and `agent.get_session_by_id(id)`. See [§9 Session Management Methods](#9-session-management-methods). |
| [#3589](https://github.com/microsoft/agent-framework/issues/3589) | Move serialize method into the agent | ✅ `agent.serialize_session(session)` and `agent.restore_session(state)`. Agent handles all serialization. See [§8 Serialization](#8-session-serializationdeserialization). |
| [#3590](https://github.com/microsoft/agent-framework/issues/3590) | Design orthogonal ChatMessageStore for service vs local | ✅ `StorageContextMiddleware` works orthogonally: configure `load_messages=False` when service manages storage. Multiple storage middleware allowed. See [§3 Unified Storage](#3-unified-storage-middleware). |
| [#3601](https://github.com/microsoft/agent-framework/issues/3601) | Rename ChatMessageStore to ChatHistoryProvider | 🔒 **Closed** - Superseded by this ADR. `ChatMessageStore` removed entirely, replaced by `StorageContextMiddleware`. |

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

The following key decisions shape the ContextPlugin design:

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Agent vs Session Ownership** | Agent owns plugin instances; Session owns state as mutable dict. Plugins shared across sessions, state isolated per session. |
| 2 | **Execution Pattern** | **ContextPlugin** with `before_run`/`after_run` methods (hooks pattern). Simpler mental model than wrapper/onion pattern. |
| 3 | **State Management** | Whole state dict (`dict[str, Any]`) passed to each plugin. Dict is mutable, so no return value needed. |
| 4 | **Default Storage at Runtime** | `InMemoryStoragePlugin` auto-added when no service_session_id, store≠True, and no plugins. Evaluated at runtime so users can modify pipeline first. |
| 5 | **Multiple Storage Allowed** | Warn at session creation if multiple or zero storage plugins have `load_messages=True` (likely misconfiguration). |
| 6 | **Single Storage Class** | One `StorageContextPlugin` configured for memory/audit/evaluation - no separate classes. |
| 7 | **Mandatory source_id** | Required parameter forces explicit naming for attribution in `context_messages` dict. |
| 8 | **Explicit Load Behavior** | `load_messages: bool = True` - explicit configuration with no automatic detection. For `StorageContextPlugin`, `before_run` is skipped entirely when `load_messages=False`. |
| 9 | **Dict-based Context** | `context_messages: dict[str, list[ChatMessage]]` keyed by source_id maintains order and enables filtering. Messages can have an `attribution` marker in `additional_properties` for external filtering scenarios. |
| 10 | **Selective Storage** | `store_context_messages` and `store_context_from` control what gets persisted from other plugins. |
| 11 | **Tool Attribution** | `add_tools()` automatically sets `tool.metadata["context_source"] = source_id`. |
| 12 | **Clean Break** | Remove `AgentThread`, `ContextProvider`, `ChatMessageStore` completely (preview, no compatibility shims). |
| 13 | **Plugin Ordering** | User-defined order; storage sees prior plugins (pre-processing) or all plugins (post-processing). |
| 14 | **Agent-owned Serialization** | `agent.serialize_session(session)` and `agent.restore_session(state)`. Agent handles all serialization. |
| 15 | **Session Management Methods** | `agent.create_session()` (no required params) and `agent.get_session_by_id(id)` for clear lifecycle management. |

## Considered Options

### Option 1: Status Quo - Keep Separate Abstractions

Keep `ContextProvider`, `ChatMessageStore`, and `AgentThread` as separate concepts.

**Pros:**
- No migration required
- Familiar to existing users
- Each concept has a clear, focused responsibility
- Existing documentation and examples remain valid

**Cons:**
- Cognitive overhead: three concepts to learn for context management
- No composability: only one `ContextProvider` per thread
- Inconsistent with middleware pattern used elsewhere in the framework
- `invoking()`/`invoked()` split makes related pre/post logic harder to follow
- No source attribution for debugging which provider added which context
- `ChatMessageStore` and `ContextProvider` overlap conceptually but are separate APIs

### Option 2: ContextMiddleware - Wrapper Pattern

Create a unified `ContextMiddleware` base class that uses the onion/wrapper pattern (like existing `AgentMiddleware`, `ChatMiddleware`) to handle all context-related concerns. This includes a `StorageContextMiddleware` subclass specifically for history persistence.

**Class hierarchy:**
- `ContextMiddleware` (base) - for general context injection (RAG, instructions, tools)
- `StorageContextMiddleware(ContextMiddleware)` - for conversation history storage (in-memory, Redis, Cosmos, etc.)

```python
class ContextMiddleware(ABC):
    def __init__(self, source_id: str, *, session_id: str | None = None):
        self.source_id = source_id
        self.session_id = session_id

    @abstractmethod
    async def process(self, context: SessionContext, next: ContextMiddlewareNext) -> None:
        """Wrap the context flow - modify before next(), process after."""
        # Pre-processing: add context, modify messages
        context.add_messages(self.source_id, [...])

        await next(context)  # Call next middleware or terminal handler

        # Post-processing: log, store, react to response
        await self.store(context.response_messages)
```

**Pros:**
- Single concept for all context engineering
- Familiar pattern from other middleware in the framework (`AgentMiddleware`, `ChatMiddleware`)
- Natural composition via pipeline with clear execution order
- Pre/post processing in one method keeps related logic together
- Source attribution built-in
- Full control over the invocation chain (can short-circuit, retry, wrap with try/catch)
- Exception handling naturally scoped to the middleware that caused it

**Cons:**
- Forgetting `await next(context)` silently breaks the chain
- Stack depth increases with each middleware layer
- Harder to implement middleware that only needs pre OR post processing

### Option 3: ContextHooks - Pre/Post Pattern

Create a `ContextHooks` base class with explicit `before_run()` and `after_run()` methods, diverging from the wrapper pattern used by middleware. This includes a `StorageContextHooks` subclass specifically for history persistence.

**Class hierarchy:**
- `ContextHooks` (base) - for general context injection (RAG, instructions, tools)
- `StorageContextHooks(ContextHooks)` - for conversation history storage (in-memory, Redis, Cosmos, etc.)

```python
class ContextHooks(ABC):
    def __init__(self, source_id: str, *, session_id: str | None = None):
        self.source_id = source_id
        self.session_id = session_id

    async def before_run(self, context: SessionContext) -> None:
        """Called before model invocation. Modify context here."""
        pass

    async def after_run(self, context: SessionContext) -> None:
        """Called after model invocation. React to response here."""
        pass
```

> **Note on naming:** Both the class name (`ContextHooks`) and method names (`before_run`/`after_run`) are open for discussion. The names used throughout this ADR are placeholders pending a final decision. See alternative naming options below.

**Alternative class naming options:**

| Name | Rationale |
|------|-----------|
| `ContextHooks` | Emphasizes the hook-based nature, familiar from React/Git hooks |
| `ContextHandler` | Generic term for something that handles context events |
| `ContextInterceptor` | Common in Java/Spring, emphasizes interception points |
| `ContextProcessor` | Emphasizes processing at defined stages |
| `ContextPlugin` | Emphasizes extensibility, familiar from build tools |
| `SessionHooks` | Ties to `AgentSession`, emphasizes session lifecycle |
| `InvokeHooks` | Directly describes what's being hooked (the invoke call) |

**Alternative method naming options:**

| before / after | Rationale |
|----------------|-----------|
| `before_run` / `after_run` | Matches `agent.run()` terminology |
| `before_invoke` / `after_invoke` | Emphasizes invocation lifecycle |
| `invoking` / `invoked` | Matches current Python `ContextProvider` and .NET naming |
| `pre_invoke` / `post_invoke` | Common prefix convention |
| `on_invoking` / `on_invoked` | Event-style naming |
| `prepare` / `finalize` | Action-oriented naming |

**Example usage:**

```python
class RAGHooks(ContextHooks):
    async def before_run(self, context: SessionContext) -> None:
        docs = await self.retrieve_documents(context.input_messages[-1].text)
        context.add_messages(self.source_id, [ChatMessage.system(f"Context: {docs}")])

    async def after_run(self, context: SessionContext) -> None:
        await self.store_interaction(context.input_messages, context.response_messages)


# Pipeline execution is linear, not nested:
# 1. hook1.before_run(context)
# 2. hook2.before_run(context)
# 3. <model invocation>
# 4. hook2.after_run(context)  # Reverse order for symmetry
# 5. hook1.after_run(context)

agent = ChatAgent(
    chat_client=client,
    context_hooks=[
        InMemoryStorageHooks("memory"),
        RAGHooks("rag"),
    ]
)
```

**Pros:**
- Simpler mental model: "before" runs before, "after" runs after - no nesting to understand
- Clearer separation between what this does vs what Agent Middleware can do.
- Impossible to forget calling `next()` - the framework handles sequencing
- Easier to implement hooks that only need one phase (just override one method)
- Lower cognitive overhead for developers new to middleware patterns
- Clearer separation of concerns: pre-processing logic separate from post-processing
- Easier to test: no need to mock `next` callable, just call methods directly
- Flatter stack traces when debugging
- More similar to the current `ContextProvider` API (`invoking`/`invoked`), easing migration
- Explicit about what happens when: no hidden control flow

**Cons:**
- Diverges from the wrapper pattern used by `AgentMiddleware` and `ChatMiddleware`
- Less powerful: cannot short-circuit the chain or implement retry logic
- No "around" advice: cannot wrap invocation in try/catch or timing block
- Exception in `before_run` may leave state inconsistent if no cleanup in `after_run`
- Two methods to implement instead of one (though both are optional)
- Harder to share state between before/after (need instance variables)
- Cannot control whether subsequent hooks run (no early termination)

## Detailed Design

This section covers the design decisions that apply to both approaches. Where the approaches differ, both are shown.

### 1. Execution Pattern

The core difference between the two options is the execution model:

**Option 2 - Middleware (Wrapper/Onion):**
```python
class ContextMiddleware(ABC):
    @abstractmethod
    async def process(self, context: SessionContext, next: ContextMiddlewareNext) -> None:
        # Pre-processing
        context.add_messages(self.source_id, [...])
        await next(context)  # Call next middleware
        # Post-processing
        await self.store(context.response_messages)
```

**Option 3 - Hooks (Linear):**
```python
class ContextHooks(ABC):
    async def before_run(self, context: SessionContext) -> None:
        """Called before model invocation."""
        context.add_messages(self.source_id, [...])

    async def after_run(self, context: SessionContext) -> None:
        """Called after model invocation."""
        await self.store(context.response_messages)
```

**Execution flow comparison:**

```
Middleware (Wrapper/Onion):            Hooks (Linear):
┌──────────────────────────┐            ┌─────────────────────────┐
│ middleware1.process()    │            │ hook1.before_run()      │
│  ┌───────────────────┐   │            │ hook2.before_run()      │
│  │ middleware2.process│  │            │ hook3.before_run()      │
│  │  ┌─────────────┐  │   │            ├─────────────────────────┤
│  │  │   invoke    │  │   │     vs     │      <invoke>           │
│  │  └─────────────┘  │   │            ├─────────────────────────┤
│  │ (post-processing) │   │            │ hook3.after_run()       │
│  └───────────────────┘   │            │ hook2.after_run()       │
│ (post-processing)        │            │ hook1.after_run()       │
└──────────────────────────┘            └─────────────────────────┘
```

### 2. Agent vs Session Ownership

Both approaches use the same ownership model:
- **Agent** owns the configuration (instances or factories)
- **AgentSession** owns the resolved pipeline (created at runtime)

**Middleware:**
```python
agent = ChatAgent(
    chat_client=client,
    context_middleware=[
        InMemoryStorageMiddleware("memory"),
        RAGContextMiddleware("rag"),
    ]
)
session = agent.create_session()
```

**Hooks:**
```python
agent = ChatAgent(
    chat_client=client,
    context_hooks=[
        InMemoryStorageHooks("memory"),
        RAGContextHooks("rag"),
    ]
)
session = agent.create_session()
```

**Comparison to Current:**
| Aspect | AgentThread (Current) | AgentSession (New) |
|--------|----------------------|-------------------|
| Storage | `message_store` attribute | Via storage middleware/hooks in pipeline |
| Context | `context_provider` attribute | Via any middleware/hooks in pipeline |
| Composition | One of each | Unlimited middleware/hooks |

### 3. Unified Storage

Instead of separate `ChatMessageStore`, storage is a subclass of the base context type:

**Middleware:**
```python
class StorageContextMiddleware(ContextMiddleware):
    def __init__(
        self,
        source_id: str,
        *,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_responses: bool = True,
        store_context_messages: bool = False,
        store_context_from: Sequence[str] | None = None,
    ): ...
```

**Hooks:**
```python
class StorageContextHooks(ContextHooks):
    def __init__(
        self,
        source_id: str,
        *,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_responses: bool = True,
        store_context_messages: bool = False,
        store_context_from: Sequence[str] | None = None,
    ): ...
```

**Load Behavior:**
- `load_messages=True` (default): Load messages from storage in `before_run`/pre-processing
- `load_messages=False`: Skip loading; for `StorageContextHooks`, the `before_run` hook is not called at all

**Comparison to Current:**
| Aspect | ChatMessageStore (Current) | Storage Middleware/Hooks (New) |
|--------|---------------------------|------------------------------|
| Load messages | Always via `list_messages()` | Configurable `load_messages` flag |
| Store messages | Always via `add_messages()` | Configurable `store_*` flags |
| What to store | All messages | Selective: inputs, responses, context |
| Injected context | Not supported | `store_context_messages=True/False` + `store_context_from=[source_ids]` for filtering |

### 4. Source Attribution via `source_id`

Both approaches require a `source_id` for attribution (identical implementation):

```python
class SessionContext:
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

**Benefits:**
- Debug which middleware/hooks added which messages
- Filter messages by source (e.g., exclude RAG from storage)
- Multiple instances of same type distinguishable

**Message-level Attribution:**

In addition to source-based filtering, individual `ChatMessage` objects should have an `attribution` marker in their `additional_properties` dict. This enables external scenarios to filter messages after the full list has been composed from input and context messages:

```python
# Setting attribution on a message
message = ChatMessage(
    role="system",
    text="Relevant context from knowledge base",
    additional_properties={"attribution": "knowledge_base"}
)

# Filtering by attribution (external scenario)
all_messages = context.get_all_messages(include_input=True)
filtered = [m for m in all_messages if m.additional_properties.get("attribution") != "ephemeral"]
```

This is useful for scenarios where filtering by `source_id` is not sufficient, such as when messages from the same source need different treatment.

> **Note:** The `attribution` marker is intended for runtime filtering only and should **not** be propagated to storage. Storage middleware should strip `attribution` from `additional_properties` before persisting messages.

### 5. Default Storage Behavior

Zero-config works out of the box (both approaches):

```python
# No middleware/hooks configured - still gets conversation history!
agent = ChatAgent(chat_client=client, name="assistant")
session = agent.create_session()
response = await agent.run("Hello!", session=session)
response = await agent.run("What did I say?", session=session)  # Remembers!
```

Default in-memory storage is added at runtime **only when**:
- No `service_session_id` (service not managing storage)
- `options.store` is not `True` (user not expecting service storage)
- **No pipeline configured at all** (pipeline is empty or None)

**Important:** If the user configures *any* middleware/hooks (even non-storage ones), the framework does **not** automatically add storage. This is intentional:
- Once users start customizing the pipeline, we consider them a advanced user and they should know what they are doing, therefore they should explicitly configure storage
- Automatic insertion would create ordering ambiguity
- Explicit configuration is clearer than implicit behavior

### 6. Instance vs Factory

Both approaches support shared instances and per-session factories:

**Middleware:**
```python
# Instance (shared across sessions)
agent = ChatAgent(context_middleware=[RAGContextMiddleware("rag")])

# Factory (new instance per session)
def create_cache(session_id: str | None) -> ContextMiddleware:
    return SessionCacheMiddleware("cache", session_id=session_id)

agent = ChatAgent(context_middleware=[create_cache])
```

**Hooks:**
```python
# Instance (shared across sessions)
agent = ChatAgent(context_hooks=[RAGContextHooks("rag")])

# Factory (new instance per session)
def create_cache(session_id: str | None) -> ContextHooks:
    return SessionCacheHooks("cache", session_id=session_id)

agent = ChatAgent(context_hooks=[create_cache])
```

### 7. Renaming: Thread → Session

`AgentThread` becomes `AgentSession` to better reflect its purpose:
- "Thread" implies a sequence of messages
- "Session" better captures the broader scope (state, pipeline, lifecycle)
- Align with recent change in .NET SDK

### 8. Session Serialization/Deserialization

Both approaches use the same agent-owned serialization pattern:

**Base class (both approaches):**
```python
# ContextMiddleware or ContextHooks - same interface
async def serialize(self) -> Any:
    """Serialize state. Default returns None (no state)."""
    return None

async def restore(self, state: Any) -> None:
    """Restore state from serialized object."""
    pass
```

**Agent methods (identical for both):**
```python
class ChatAgent:
    async def serialize_session(self, session: AgentSession) -> dict[str, Any]:
        """Serialize a session's state for persistence."""
        middleware_states: dict[str, Any] = {}
        if session.context_pipeline:
            for item in session.context_pipeline:
                state = await item.serialize()
                if state is not None:
                    middleware_states[item.source_id] = state
        return {
            "session_id": session.session_id,
            "service_session_id": session.service_session_id,
            "middleware_states": middleware_states,
        }

    async def restore_session(self, serialized: dict[str, Any]) -> AgentSession:
        """Restore a session from serialized state."""
        ...
```

### 9. Session Management Methods

Both approaches use identical agent methods:

```python
class ChatAgent:
    def create_session(
        self,
        *,
        session_id: str | None = None,
        service_session_id: str | None = None,
    ) -> AgentSession:
        """Create a new session with a fresh pipeline."""
        ...

    def get_session_by_id(self, session_id: str) -> AgentSession:
        """Get a session by ID with a fresh pipeline."""
        return self.create_session(session_id=session_id)

    async def serialize_session(self, session: AgentSession) -> dict[str, Any]: ...
    async def restore_session(self, serialized: dict[str, Any]) -> AgentSession: ...
```

**Usage (identical for both):**
```python
session = agent.create_session()
session = agent.create_session(session_id="user-123-session-456")
session = agent.create_session(service_session_id="thread_abc123")
session = agent.get_session_by_id("existing-session-id")
session = await agent.restore_session(state)
```

### 10. Accessing Context from Other Middleware/Hooks

Non-storage middleware/hooks can read context added by others via `context.context_messages`. However, they should operate under the assumption that **only the current input messages are available** - there is no implicit conversation history.

If historical context is needed (e.g., RAG using last few messages), maintain a **self-managed buffer**, which would look something like this:

**Middleware:**
```python
class RAGWithBufferMiddleware(ContextMiddleware):
    def __init__(self, source_id: str, retriever: Retriever, *, buffer_window: int = 5):
        super().__init__(source_id)
        self._retriever = retriever
        self._buffer_window = buffer_window
        self._message_buffer: list[ChatMessage] = []

    async def process(self, context: SessionContext, next: ContextMiddlewareNext) -> None:
        # Use buffer + current input for retrieval
        recent = self._message_buffer[-self._buffer_window * 2:]
        query = self._build_query(recent + list(context.input_messages))
        docs = await self._retriever.search(query)
        context.add_messages(self.source_id, [ChatMessage.system(f"Context: {docs}")])

        await next(context)

        # Update buffer
        self._message_buffer.extend(context.input_messages)
        if context.response_messages:
            self._message_buffer.extend(context.response_messages)
```

**Hooks:**
```python
class RAGWithBufferHooks(ContextHooks):
    def __init__(self, source_id: str, retriever: Retriever, *, buffer_window: int = 5):
        super().__init__(source_id)
        self._retriever = retriever
        self._buffer_window = buffer_window
        self._message_buffer: list[ChatMessage] = []

    async def before_run(self, context: SessionContext) -> None:
        recent = self._message_buffer[-self._buffer_window * 2:]
        query = self._build_query(recent + list(context.input_messages))
        docs = await self._retriever.search(query)
        context.add_messages(self.source_id, [ChatMessage.system(f"Context: {docs}")])

    async def after_run(self, context: SessionContext) -> None:
        self._message_buffer.extend(context.input_messages)
        if context.response_messages:
            self._message_buffer.extend(context.response_messages)
```

**Simple RAG (input only, no buffer):**

```python
# Middleware
async def process(self, context, next):
    query = " ".join(msg.text for msg in context.input_messages if msg.text)
    docs = await self._retriever.search(query)
    context.add_messages(self.source_id, [ChatMessage.system(f"Context: {docs}")])
    await next(context)

# Hooks
async def before_run(self, context):
    query = " ".join(msg.text for msg in context.input_messages if msg.text)
    docs = await self._retriever.search(query)
    context.add_messages(self.source_id, [ChatMessage.system(f"Context: {docs}")])
```

### Migration Impact

| Current | Middleware (Option 2) | Hooks (Option 3) |
|---------|----------------------|------------------|
| `ContextProvider` | `ContextMiddleware` | `ContextHooks` |
| `invoking()` | Before `await next(context)` | `before_run()` |
| `invoked()` | After `await next(context)` | `after_run()` |
| `ChatMessageStore` | `StorageContextMiddleware` | `StorageContextHooks` |
| `AgentThread` | `AgentSession` | `AgentSession` |

### Example: Current vs New

**Current:**
```python
class MyContextProvider(ContextProvider):
    async def invoking(self, messages, **kwargs) -> Context:
        docs = await self.retrieve_documents(messages[-1].text)
        return Context(messages=[ChatMessage.system(f"Context: {docs}")])

    async def invoked(self, request, response, **kwargs) -> None:
        await self.store_interaction(request, response)

thread = await agent.get_new_thread(message_store=ChatMessageStore())
thread.context_provider = provider
response = await agent.run("Hello", thread=thread)
```

**New (Middleware):**
```python
class RAGMiddleware(ContextMiddleware):
    async def process(self, context: SessionContext, next) -> None:
        docs = await self.retrieve_documents(context.input_messages[-1].text)
        context.add_messages(self.source_id, [ChatMessage.system(f"Context: {docs}")])
        await next(context)
        await self.store_interaction(context.input_messages, context.response_messages)

agent = ChatAgent(
    chat_client=client,
    context_middleware=[InMemoryStorageMiddleware("memory"), RAGMiddleware("rag")]
)
session = agent.create_session()
response = await agent.run("Hello", session=session)
```

**New (Hooks):**
```python
class RAGHooks(ContextHooks):
    async def before_run(self, context: SessionContext) -> None:
        docs = await self.retrieve_documents(context.input_messages[-1].text)
        context.add_messages(self.source_id, [ChatMessage.system(f"Context: {docs}")])

    async def after_run(self, context: SessionContext) -> None:
        await self.store_interaction(context.input_messages, context.response_messages)

agent = ChatAgent(
    chat_client=client,
    context_hooks=[InMemoryStorageHooks("memory"), RAGHooks("rag")]
)
session = agent.create_session()
response = await agent.run("Hello", session=session)
```
## Decision Outcome

### Decision 1: Execution Pattern

**Chosen: Option 3 - Hooks (Pre/Post Pattern)** with the following naming:
- **Class name:** `ContextPlugin` (emphasizes extensibility, familiar from build tools)
- **Method names:** `before_run` / `after_run` (matches `agent.run()` terminology)

Rationale:
- Simpler mental model: "before" runs before, "after" runs after - no nesting to understand
- Easier to implement plugins that only need one phase (just override one method)
- More similar to the current `ContextProvider` API (`invoking`/`invoked`), easing migration
- Clearer separation between what this does vs what Agent Middleware can do

Both options share the same:
- Agent vs Session ownership model
- `source_id` attribution
- Serialization/deserialization via agent methods
- Session management methods (`create_session`, `get_session_by_id`, `serialize_session`, `restore_session`)
- Renaming `AgentThread` → `AgentSession`

### Decision 2: Instance Ownership (Orthogonal)

**Chosen: Option B1 - Instances in Agent, State in Session (Simple Dict)**

The `ChatAgent` owns and manages the `ContextPlugin` instances. The `AgentSession` only stores state as a mutable `dict[str, Any]`. Each plugin receives the **whole state dict** (not just its own slice), and since a dict is mutable, no return value is needed - plugins modify the dict in place.

> **Note on trust:** Since all `ContextPlugin` instances reason over conversation messages (which may contain sensitive user data), they should be **trusted by default**. This is also why we allow all plugins to see all state - if a plugin is untrusted, it shouldn't be in the pipeline at all. The whole state dict is passed rather than isolated slices because plugins that handle messages already have access to the full conversation context.

Rationale for B1 over B2: Simpler is better. The whole state dict is passed to each plugin, and since Python dicts are mutable, plugins can modify state in place without returning anything. This is the most Pythonic approach.

Rationale for B over A:
- Lightweight sessions - just data, easy to serialize/transfer
- Plugin instances shared across sessions (more memory efficient)
- Clearer separation: agent = behavior, session = state
- Factories not needed - state dict handles per-session needs

### Instance Ownership Options (for reference)

#### Option A: Instances in Session

The `AgentSession` owns the actual middleware/hooks instances. The pipeline is created when the session is created, and instances are stored in the session.

```python
class AgentSession:
    """Session owns the middleware instances."""

    def __init__(
        self,
        *,
        session_id: str | None = None,
        context_pipeline: ContextMiddlewarePipeline | None = None,  # Owns instances
    ):
        self._session_id = session_id or str(uuid.uuid4())
        self._context_pipeline = context_pipeline  # Actual instances live here


class ChatAgent:
    def __init__(
        self,
        chat_client: ...,
        *,
        context_middleware: Sequence[ContextMiddlewareConfig] | None = None,
    ):
        self._context_middleware_config = list(context_middleware or [])

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        """Create session with resolved middleware instances."""
        resolved_id = session_id or str(uuid.uuid4())

        # Resolve factories and create actual instances
        pipeline = None
        if self._context_middleware_config:
            pipeline = ContextMiddlewarePipeline.from_config(
                self._context_middleware_config,
                session_id=resolved_id,
            )

        return AgentSession(
            session_id=resolved_id,
            context_pipeline=pipeline,  # Session owns the instances
        )

    async def run(self, input: str, *, session: AgentSession) -> AgentResponse:
        # Session's pipeline executes
        context = await session.run_context_pipeline(input_messages)
        # ... invoke model ...
```

**Pros:**
- Self-contained session - all state and behavior together
- Middleware can maintain per-session instance state naturally
- Session given to another agent will work the same way

**Cons:**
- Session becomes heavier (instances + state)
- Complicated serialization - serialization needs to deal with instances, which might include non-serializable things like clients or connections
- Harder to share stateless middleware across sessions efficiently
- Factories must be re-resolved for each session

#### Option B: Instances in Agent, State in Session (CHOSEN)

The `ChatAgent` owns and manages the middleware/hooks instances. The `AgentSession` only stores state data that middleware reads/writes. The agent's runner executes the pipeline using the session's state.

Two variants exist for how state is stored in the session:

##### Option B1: Simple Dict State (CHOSEN)

The session stores state as a simple `dict[str, Any]`. Each plugin receives the **whole state dict**, and since dicts are mutable in Python, plugins can modify it in place without needing to return a value.

```python
class AgentSession:
    """Session only holds state as a simple dict."""

    def __init__(self, *, session_id: str | None = None):
        self._session_id = session_id or str(uuid.uuid4())
        self.service_session_id: str | None = None
        self.state: dict[str, Any] = {}  # Mutable state dict


class ChatAgent:
    def __init__(
        self,
        chat_client: ...,
        *,
        context_plugins: Sequence[ContextPlugin] | None = None,
    ):
        # Agent owns the actual plugin instances
        self._context_plugins = list(context_plugins or [])

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        """Create lightweight session with just state."""
        return AgentSession(session_id=session_id)

    async def run(self, input: str, *, session: AgentSession) -> AgentResponse:
        context = SessionContext(
            session_id=session.session_id,
            input_messages=[...],
        )

        # Before-run plugins
        for plugin in self._context_plugins:
            await plugin.before_run(self, session, context, session.state)

        # assemble final input messages from context

        # ... actual running, i.e. `get_response` for ChatAgent ...

        # After-run plugins (reverse order)
        for plugin in reversed(self._context_plugins):
            await plugin.after_run(self, session, context, session.state)


# Plugin that maintains state - modifies dict in place
class InMemoryStoragePlugin(ContextPlugin):
    async def before_run(
        self,
        agent: "ChatAgent",
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        # Read from state (use source_id as key for namespace)
        my_state = state.get(self.source_id, {})
        messages = my_state.get("messages", [])
        context.add_messages(self.source_id, messages)

    async def after_run(
        self,
        agent: "ChatAgent",
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        # Modify state dict in place - no return needed
        my_state = state.setdefault(self.source_id, {})
        messages = my_state.get("messages", [])
        my_state["messages"] = [
            *messages,
            *context.input_messages,
            *(context.response_messages or []),
        ]


# Stateless plugin - ignores state
class TimeContextPlugin(ContextPlugin):
    async def before_run(
        self,
        agent: "ChatAgent",
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        context.add_instructions(self.source_id, f"Current time: {datetime.now()}")

    async def after_run(
        self,
        agent: "ChatAgent",
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        pass  # No state, nothing to do after
```

##### Option B2: SessionState Object

The session stores state in a dedicated `SessionState` object. Each hook receives its own state slice through a mutable wrapper that writes back automatically.

```python
class HookState:
    """Mutable wrapper for a single hook's state.

    Changes are written back to the session state automatically.
    """

    def __init__(self, session_state: dict[str, dict[str, Any]], source_id: str):
        self._session_state = session_state
        self._source_id = source_id
        if source_id not in session_state:
            session_state[source_id] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._session_state[self._source_id].get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._session_state[self._source_id][key] = value

    def update(self, values: dict[str, Any]) -> None:
        self._session_state[self._source_id].update(values)


class SessionState:
    """Structured state container for a session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.service_session_id: str | None = None
        self._hook_state: dict[str, dict[str, Any]] = {}  # source_id -> state

    def get_hook_state(self, source_id: str) -> HookState:
        """Get mutable state wrapper for a specific hook."""
        return HookState(self._hook_state, source_id)


class AgentSession:
    """Session holds a SessionState object."""

    def __init__(self, *, session_id: str | None = None):
        self._session_id = session_id or str(uuid.uuid4())
        self._state = SessionState(self._session_id)

    @property
    def state(self) -> SessionState:
        return self._state


class ContextHooksRunner:
    """Agent-owned runner that executes hooks with session state."""

    def __init__(self, hooks: Sequence[ContextHooks]):
        self._hooks = list(hooks)

    async def run_before(
        self,
        context: SessionContext,
        session_state: SessionState,
    ) -> None:
        """Run before_run for all hooks."""
        for hook in self._hooks:
            my_state = session_state.get_hook_state(hook.source_id)
            await hook.before_run(context, my_state)

    async def run_after(
        self,
        context: SessionContext,
        session_state: SessionState,
    ) -> None:
        """Run after_run for all hooks in reverse order."""
        for hook in reversed(self._hooks):
            my_state = session_state.get_hook_state(hook.source_id)
            await hook.after_run(context, my_state)


# Hook uses HookState wrapper - no return needed
class InMemoryStorageHooks(ContextHooks):
    async def before_run(
        self,
        context: SessionContext,
        state: HookState,  # Mutable wrapper
    ) -> None:
        messages = state.get("messages", [])
        context.add_messages(self.source_id, messages)

    async def after_run(
        self,
        context: SessionContext,
        state: HookState,  # Mutable wrapper
    ) -> None:
        messages = state.get("messages", [])
        state.set("messages", [
            *messages,
            *context.input_messages,
            *(context.response_messages or []),
        ])


# Stateless hook - state wrapper provided but not used
class TimeContextHooks(ContextHooks):
    async def before_run(
        self,
        context: SessionContext,
        state: HookState,
    ) -> None:
        context.add_instructions(self.source_id, f"Current time: {datetime.now()}")

    async def after_run(
        self,
        context: SessionContext,
        state: HookState,
    ) -> None:
        pass  # Nothing to do
```

**Option B Pros (both variants):**
- Lightweight sessions - just data, easy to serialize/transfer
- Plugin instances shared across sessions (more memory efficient)
- Clearer separation: agent = behavior, session = state

**Option B Cons (both variants):**
- More complex execution model (agent + session coordination)
- Plugins must explicitly read/write state (no implicit instance variables)
- Session given to another agent may not work (different plugins configuration)

**B1 vs B2:**

| Aspect | B1: Simple Dict (CHOSEN) | B2: SessionState Object |
|--------|-----------------|-------------------------|
| Simplicity | Simpler, less abstraction | More structure, helper methods |
| State passing | Whole dict passed, mutate in place | Mutable wrapper, no return needed |
| Type safety | `dict[str, Any]` - loose | Can add type hints on methods |
| Extensibility | Add keys as needed | Can add methods/validation |
| Serialization | Direct JSON serialization | Need custom serialization |

#### Comparison

| Aspect | Option A: Instances in Session | Option B: Instances in Agent (CHOSEN) |
|--------|-------------------------------|------------------------------|
| Session weight | Heavier (instances + state) | Lighter (state only) |
| Plugin sharing | Per-session instances | Shared across sessions |
| Instance state | Natural (instance variables) | Explicit (state dict) |
| Serialization | Serialize session + plugins | Serialize state only |
| Factory handling | Resolved at session creation | Not needed (state dict handles per-session needs) |
| Signature | `before_run(context)` | `before_run(agent, session, context, state)` |
| Session portability | Works with any agent | Tied to agent's plugins config |

#### Factories Not Needed with Option B

With Option B (instances in agent, state in session), the plugins are shared across sessions and the explicit state dict handles per-session needs. Therefore, **factory support is not needed**:

- State is externalized to the session's `state: dict[str, Any]`
- If a plugin needs per-session initialization, it can do so in `before_run` on first call (checking if state is empty)
- All plugins are shared across sessions (more memory efficient)
- Plugins use `state.setdefault(self.source_id, {})` to namespace their state

---

## Comparison to .NET Implementation

The .NET Agent Framework provides equivalent functionality through a different structure. Both implementations achieve the same goals using idioms natural to their respective languages.

### Concept Mapping

| .NET Concept | Python (Chosen) |
|--------------|-----------------|
| `AIContextProvider` | `ContextPlugin` |
| `ChatHistoryProvider` | `StorageContextPlugin` |
| `AgentSession` | `AgentSession` |

### Feature Equivalence

Both platforms provide the same core capabilities:

| Capability | .NET | Python |
|------------|------|--------|
| Inject context before invocation | `AIContextProvider.InvokingAsync()` | `ContextPlugin.before_run()` |
| React after invocation | `AIContextProvider.InvokedAsync()` | `ContextPlugin.after_run()` |
| Load conversation history | `ChatHistoryProvider.InvokingAsync()` | `StorageContextPlugin` with `load_messages=True` |
| Store conversation history | `ChatHistoryProvider.InvokedAsync()` | `StorageContextPlugin` with `store_*` flags |
| Session serialization | `Serialize()` on providers | Session's `state` dict is directly serializable |
| Factory-based creation | `AIContextProviderFactory`, `ChatHistoryProviderFactory` | Not needed - state dict handles per-session needs |

### Implementation Differences

The implementations differ in ways idiomatic to each language:

| Aspect | .NET Approach | Python Approach |
|--------|---------------|-----------------|
| **Context providers** | Separate `AIContextProvider` (single) and `ChatHistoryProvider` (single) | Unified list of `ContextPlugin` (multiple) |
| **Composition** | One of each provider type per session | Unlimited plugins in pipeline |
| **Type system** | Strict interfaces, compile-time checks | Duck typing, protocols, runtime flexibility |
| **Configuration** | DI container, factory delegates | Direct instantiation, list of instances |
| **State management** | Instance state in providers | Explicit state dict in session |
| **Default storage** | Can auto-inject when `ChatHistoryProvider` missing | Only auto-injects when no plugins configured |
| **Source tracking** | Via separate provider types | Built-in `source_id` on each plugin |

### Design Trade-offs

Each approach has trade-offs that align with language conventions:

**.NET's separate provider types:**
- Clearer separation between context injection and history storage
- Easier to detect "missing storage" and auto-inject defaults
- Type system enforces single provider of each type

**Python's unified pipeline:**
- Single abstraction for all context concerns
- Multiple instances of same type (e.g., multiple storage backends)
- More explicit - customization means owning full configuration
- `source_id` enables filtering/debugging across all sources
- Explicit state dict makes serialization trivial

Neither approach is inherently better - they reflect different language philosophies while achieving equivalent functionality. The Python design embraces the "we're all consenting adults" philosophy, while .NET provides more compile-time guardrails.

---

## Open Discussion: Context Compaction

### Problem Statement

A common need for long-running agents is **context compaction** - automatically summarizing or truncating conversation history when approaching token limits. This is particularly important for agents that make many tool calls in succession (10s or 100s), where the context can grow unboundedly.

Currently, this is challenging because:
- `ChatMessageStore.list_messages()` is only called once at the start of `agent.run()`, not during the tool loop
- `ChatMiddleware` operates on a copy of messages, so modifications don't persist across tool loop iterations
- The function calling loop happens deep within the `ChatClient`, which is below the agent level

### Design Question

Should `ContextPlugin` be invoked:
1. **Only at agent invocation boundaries** (current proposal) - before/after each `agent.run()` call
2. **During the tool loop** - before/after each model call within a single `agent.run()`

### Boundary vs In-Run Compaction

While boundary and in-run compaction could potentially use the same mechanism, they have **different goals and behaviors**:

**Boundary compaction** (before/after `agent.run()`):
- **Before run**: Keep context manageable - load a compacted view of history
- **After run**: Keep storage compact - summarize/truncate before persisting
- Useful for maintaining reasonable context sizes across conversation turns
- One reason to have **multiple storage plugins**: persist compacted history for use during runs, while also storing the full uncompacted history for auditing and evaluations

**In-run compaction** (during function calling loops):
- Relevant for **function calling scenarios** where many tool calls accumulate
- Typically **in-memory only** - no need to persist intermediate compaction and only useful when the conversation/session is _not_ managed by the service
- Different strategies apply:
  - Remove old function call/result pairs entirely/Keep only the most recent N tool interactions
  - Replace call/result pairs with a single summary message (with a different role)
  - Summarize several function call/result pairs into one larger context message

### Service-Managed vs Local Storage

**Important:** In-run compaction is relevant only for **non-service-managed histories**. When using service-managed storage (`service_session_id` is set):
- The service handles history management internally
- Only the new calls and results are sent to/from the service each turn
- The service is responsible for its own compaction strategy, but we do not control that

For local storage, a full message list is sent to the model each time, making compaction the client's responsibility.

### Options

**Option A: Invocation-boundary only (current proposal)**
- Simpler mental model
- Consistent with `AgentMiddleware` pattern
- In-run compaction would need to happen via a separate mechanism (e.g., `ChatMiddleware` at the client level)
- Risk: Different compaction mechanisms at different layers could be confusing

**Option B: Also during tool loops**
- Single mechanism for all context manipulation
- More powerful but more complex
- Requires coordination with `ChatClient` internals
- Risk: Performance overhead if plugins are expensive

**Option C: Unified approach across layers**
- Define a single context compaction abstraction that works at both agent and client levels
- `ContextPlugin` could delegate to `ChatMiddleware` for mid-loop execution
- Requires deeper architectural thought

### Potential Extension Points (for any option)

Regardless of the chosen approach, these extension points could support compaction:
- A `CompactionStrategy` that can be shared between plugins and function calling configuration
- Hooks for `ChatClient` to notify the agent layer when context limits are approaching
- A unified `ContextManager` that coordinates compaction across layers
- **Message-level attribution**: The `attribution` marker in `ChatMessage.additional_properties` can be used during compaction to identify messages that should be preserved (e.g., `attribution: "important"`) or that are safe to remove (e.g., `attribution: "ephemeral"`). This prevents accidental filtering of critical context during aggressive compaction.

> **Note:** The .NET SDK currently has a `ChatReducer` interface for context reduction/compaction. We should consider adopting similar naming in Python (e.g., `ChatReducer` or `ContextReducer`) for cross-platform consistency.

**This section requires further discussion.**

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
        response_messages: After invocation, contains the agent's response (set by agent).
            READ-ONLY - modifications are ignored. Use AgentMiddleware to modify responses.
        options: Options passed to agent.run() - READ-ONLY, for reflection only
        metadata: Shared metadata dictionary for cross-middleware communication

    Note:
        - `options` is read-only; changes will NOT be merged back into the agent run
        - `response_messages` is read-only; use AgentMiddleware to modify responses
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
    - `load_messages=True` (default): Load messages from storage
    - `load_messages=False`: Never load (audit/logging mode)

    Storage behavior:
    - `store_inputs`: Store input messages (default True)
    - `store_responses`: Store response messages (default True)
    - Storage always happens unless explicitly disabled, regardless of load_messages

    Warning: At session creation time, a warning is logged if:
    - Multiple storage middleware have `load_messages=True` (likely duplicate loading)
    - Zero storage middleware have `load_messages=True` (likely missing primary storage)

    These are warnings only (not errors) because valid use cases exist for both scenarios,
    such as intentional multi-source loading or audit-only storage configurations.

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
        load_messages: bool = True,
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
        if self.load_messages:
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
        """Warn if storage middleware configuration looks like a mistake.

        These are warnings only (not errors) because valid use cases exist
        for both multiple loaders and zero loaders.
        """
        storage_middleware = [
            m for m in self._middleware
            if isinstance(m, StorageContextMiddleware)
        ]

        if not storage_middleware:
            # No storage middleware at all - that's fine, user may not need it
            return

        loaders = [m for m in storage_middleware if m.load_messages is True]

        if len(loaders) > 1:
            warnings.warn(
                f"Multiple storage middleware configured to load messages: "
                f"{[m.source_id for m in loaders]}. "
                f"This may cause duplicate messages in context. "
                f"If this is intentional, you can ignore this warning.",
                UserWarning
            )
        elif len(loaders) == 0:
            warnings.warn(
                f"Storage middleware configured but none have load_messages=True: "
                f"{[m.source_id for m in storage_middleware]}. "
                f"No conversation history will be loaded. "
                f"If this is intentional (e.g., audit-only), you can ignore this warning.",
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

    Note: The session is created by calling agent.create_session(), which constructs
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

        Note: Prefer using agent.create_session() instead of direct construction.

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

    def create_session(
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
session = agent.create_session()
response = await agent.run("Hello, my name is Alice!", session=session)

# Conversation history is preserved automatically
response = await agent.run("What's my name?", session=session)
# Agent remembers: "Your name is Alice!"

# With service-managed session - no default storage added (service handles it)
service_session = agent.create_session()

# With store=True in options - user expects service storage, no default added
response = await agent.run("Hello!", session=session, options={"store": True})

# User can manually add middleware to session before first run
session = agent.create_session()
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
session = agent.create_session()
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
session1 = agent.create_session()
session2 = agent.create_session()
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
# load_messages=True (default) - loads and stores messages
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
        memory_middleware,   # First: loads history
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

### Example 5: Explicit Storage Configuration for Service-Managed Sessions

```python
# StorageContextMiddleware uses explicit configuration - no automatic detection.
# load_messages=True (default): Load messages from storage
# load_messages=False: Skip loading (useful for audit-only storage)

agent = ChatAgent(
    chat_client=client,
    context_middleware=[
        RedisStorageMiddleware(
            source_id="memory",
            redis_url="redis://...",
            # load_messages=True is the default
        )
    ]
)

session = agent.create_session()

# Normal run - loads and stores messages
response = await agent.run("Hello!", session=session)

# For service-managed sessions, configure storage explicitly:
# - Use load_messages=False when service handles history
service_storage = RedisStorageMiddleware(
    source_id="audit",
    redis_url="redis://...",
    load_messages=False,  # Don't load - service manages history
)

agent_with_service = ChatAgent(
    chat_client=client,
    context_middleware=[service_storage]
)
service_session = agent_with_service.create_session(service_session_id="thread_abc123")
response = await agent_with_service.run("Hello!", session=service_session)
# Storage middleware stores for audit but doesn't load (service handles history)
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
- [ ] Implement pipeline validation (warn if multiple or zero storage middleware have `load_messages=True`)
- [ ] Add `serialize()` and `restore()` methods to `ContextMiddleware` base class

#### Phase 2: AgentSession Implementation
- [ ] Create `AgentSession` class with `context_pipeline` attribute
- [ ] Add `context_middleware: Sequence[ContextMiddlewareConfig]` parameter to `BaseAgent` and `ChatAgent`
- [ ] Implement `create_session()` that resolves factories and creates pipeline
- [ ] Wire up context pipeline execution in agent invocation flow
- [ ] Implement `AgentSession.serialize()` to capture middleware states
- [ ] Implement `Agent.restore_session()` to reconstruct session from serialized state
- [ ] Remove `AgentThread` completely (no alias, clean break)

#### Phase 3: Built-in Middleware
- [ ] Create `InMemoryStorageMiddleware` (replaces `ChatMessageStore`)
- [ ] Implement `serialize()`/`restore()` for `InMemoryStorageMiddleware`
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
- [ ] Unit tests for pipeline validation warnings (multiple/zero loaders)
- [ ] Unit tests for source attribution (mandatory source_id)
- [ ] Unit tests for `store_context_messages` and `store_context_from` options
- [ ] Unit tests for session serialization/deserialization
- [ ] Integration tests for full agent flow with middleware
