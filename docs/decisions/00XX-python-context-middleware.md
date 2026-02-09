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

The following key decisions shape the ContextProvider design:

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Agent vs Session Ownership** | Agent owns plugin instances; Session owns state as mutable dict. Plugins shared across sessions, state isolated per session. |
| 2 | **Execution Pattern** | **ContextProvider** with `before_run`/`after_run` methods (hooks pattern). Simpler mental model than wrapper/onion pattern. |
| 3 | **State Management** | Whole state dict (`dict[str, Any]`) passed to each plugin. Dict is mutable, so no return value needed. |
| 4 | **Default Storage at Runtime** | `InMemoryHistoryProvider` auto-added when no service_session_id, store≠True, and no plugins. Evaluated at runtime so users can modify pipeline first. |
| 5 | **Multiple Storage Allowed** | Warn at session creation if multiple or zero history providers have `load_messages=True` (likely misconfiguration). |
| 6 | **Single Storage Class** | One `HistoryProvider` configured for memory/audit/evaluation - no separate classes. |
| 7 | **Mandatory source_id** | Required parameter forces explicit naming for attribution in `context_messages` dict. |
| 8 | **Explicit Load Behavior** | `load_messages: bool = True` - explicit configuration with no automatic detection. For `HistoryProvider`, `before_run` is skipped entirely when `load_messages=False`. |
| 9 | **Dict-based Context** | `context_messages: dict[str, list[ChatMessage]]` keyed by source_id maintains order and enables filtering. Messages can have an `attribution` marker in `additional_properties` for external filtering scenarios. |
| 10 | **Selective Storage** | `store_context_messages` and `store_context_from` control what gets persisted from other plugins. |
| 11 | **Tool Attribution** | `add_tools()` automatically sets `tool.metadata["context_source"] = source_id`. |
| 12 | **Clean Break** | Remove `AgentThread`, old `ContextProvider`, `ChatMessageStore` completely; replace with new `ContextProvider` (hooks pattern), `HistoryProvider`, `AgentSession`. No compatibility shims (preview). |
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
- **Class name:** `ContextProvider` (emphasizes extensibility, familiar from build tools)
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

The `ChatAgent` owns and manages the `ContextProvider` instances. The `AgentSession` only stores state as a mutable `dict[str, Any]`. Each plugin receives the **whole state dict** (not just its own slice), and since a dict is mutable, no return value is needed - plugins modify the dict in place.

> **Note on trust:** Since all `ContextProvider` instances reason over conversation messages (which may contain sensitive user data), they should be **trusted by default**. This is also why we allow all plugins to see all state - if a plugin is untrusted, it shouldn't be in the pipeline at all. The whole state dict is passed rather than isolated slices because plugins that handle messages already have access to the full conversation context.

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
        context_providers: Sequence[ContextProvider] | None = None,
    ):
        # Agent owns the actual plugin instances
        self._context_providers = list(context_providers or [])

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        """Create lightweight session with just state."""
        return AgentSession(session_id=session_id)

    async def run(self, input: str, *, session: AgentSession) -> AgentResponse:
        context = SessionContext(
            session_id=session.session_id,
            input_messages=[...],
        )

        # Before-run plugins
        for plugin in self._context_providers:
            await plugin.before_run(self, session, context, session.state)

        # assemble final input messages from context

        # ... actual running, i.e. `get_response` for ChatAgent ...

        # After-run plugins (reverse order)
        for plugin in reversed(self._context_providers):
            await plugin.after_run(self, session, context, session.state)


# Plugin that maintains state - modifies dict in place
class InMemoryHistoryProvider(ContextProvider):
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
class TimeContextProvider(ContextProvider):
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
| `AIContextProvider` | `ContextProvider` |
| `ChatHistoryProvider` | `HistoryProvider` |
| `AgentSession` | `AgentSession` |

### Feature Equivalence

Both platforms provide the same core capabilities:

| Capability | .NET | Python |
|------------|------|--------|
| Inject context before invocation | `AIContextProvider.InvokingAsync()` | `ContextProvider.before_run()` |
| React after invocation | `AIContextProvider.InvokedAsync()` | `ContextProvider.after_run()` |
| Load conversation history | `ChatHistoryProvider.InvokingAsync()` | `HistoryProvider` with `load_messages=True` |
| Store conversation history | `ChatHistoryProvider.InvokedAsync()` | `HistoryProvider` with `store_*` flags |
| Session serialization | `Serialize()` on providers | Session's `state` dict is directly serializable |
| Factory-based creation | `AIContextProviderFactory`, `ChatHistoryProviderFactory` | Not needed - state dict handles per-session needs |

### Implementation Differences

The implementations differ in ways idiomatic to each language:

| Aspect | .NET Approach | Python Approach |
|--------|---------------|-----------------|
| **Context providers** | Separate `AIContextProvider` (single) and `ChatHistoryProvider` (single) | Unified list of `ContextProvider` (multiple) |
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

See **Appendix A** for class hierarchy, API signatures, and user experience examples.
See the **Workplan** at the end for PR breakdown and reference implementation.

---

## Appendix A: API Overview

### Class Hierarchy

```
ContextProvider (base - hooks pattern)
├── HistoryProvider (storage subclass)
│   ├── InMemoryHistoryProvider (built-in)
│   ├── RedisHistoryProvider (packages/redis)
│   └── CosmosHistoryProvider (packages/azure-ai)
├── AzureAISearchContextProvider (packages/azure-ai-search)
├── Mem0ContextProvider (packages/mem0)
└── (custom user providers)

AgentSession (lightweight state container)

SessionContext (per-invocation state)
```

### ContextProvider

```python
class ContextProvider(ABC):
    """Base class for context providers (hooks pattern).

    Context providers participate in the context engineering pipeline,
    adding context before model invocation and processing responses after.

    Attributes:
        source_id: Unique identifier for this provider instance (required).
            Used for message/tool attribution so other providers can filter.
    """

    def __init__(self, source_id: str):
        self.source_id = source_id

    async def before_run(
        self,
        agent: "ChatAgent",
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Called before model invocation. Override to add context."""
        pass

    async def after_run(
        self,
        agent: "ChatAgent",
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Called after model invocation. Override to process response."""
        pass

    async def serialize(self) -> Any:
        """Serialize provider state. Default returns None (no state)."""
        return None

    async def restore(self, state: Any) -> None:
        """Restore provider state from serialized object."""
        pass
```

### HistoryProvider

```python
class HistoryProvider(ContextProvider):
    """Base class for conversation history storage providers.

    A single class configured for different use cases:
    - Primary memory storage (loads + stores messages)
    - Audit/logging storage (stores only, doesn't load)
    - Evaluation storage (stores only for later analysis)

    Loading behavior:
    - `load_messages=True` (default): Load messages from storage in before_run
    - `load_messages=False`: Skip loading (before_run is a no-op)

    Storage behavior:
    - `store_inputs`: Store input messages (default True)
    - `store_responses`: Store response messages (default True)
    - `store_context_messages`: Also store context from other providers (default False)
    - `store_context_from`: Only store from specific source_ids (default None = all)
    """

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

    @abstractmethod
    async def get_messages(self, session_id: str | None) -> list[ChatMessage]:
        """Retrieve stored messages for this session."""
        ...

    @abstractmethod
    async def save_messages(self, session_id: str | None, messages: Sequence[ChatMessage]) -> None:
        """Persist messages for this session."""
        ...
```

### SessionContext

```python
class SessionContext:
    """Per-invocation state passed through the context provider pipeline.

    Created fresh for each agent.run() call. Providers read from and write to
    the mutable fields to add context before invocation and process responses after.

    Attributes:
        session_id: The ID of the current session
        service_session_id: Service-managed session ID (if present)
        input_messages: New messages being sent to the agent (set by caller)
        context_messages: Dict mapping source_id -> messages added by that provider.
            Maintains insertion order (provider execution order).
        instructions: Additional instructions - providers can append here
        tools: Additional tools - providers can append here
        response_messages: After invocation, contains the agent's response (set by agent).
            READ-ONLY - use AgentMiddleware to modify responses.
        options: Options passed to agent.run() - READ-ONLY, for reflection only
        metadata: Shared metadata dictionary for cross-provider communication
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
    ): ...

    def add_messages(self, source_id: str, messages: Sequence[ChatMessage]) -> None:
        """Add context messages from a specific source."""
        ...

    def add_instructions(self, source_id: str, instructions: str | Sequence[str]) -> None:
        """Add instructions to be prepended to the conversation."""
        ...

    def add_tools(self, source_id: str, tools: Sequence[ToolProtocol]) -> None:
        """Add tools with source attribution in tool.metadata."""
        ...

    def get_messages(
        self,
        sources: Sequence[str] | None = None,
        exclude_sources: Sequence[str] | None = None,
    ) -> list[ChatMessage]:
        """Get context messages, optionally filtered by source."""
        ...

    def get_all_messages(
        self,
        *,
        include_input: bool = False,
        include_response: bool = False,
    ) -> list[ChatMessage]:
        """Get all messages (context + optionally input + response)."""
        ...
```

### AgentSession (Decision B1)

```python
class AgentSession:
    """A conversation session with an agent.

    Lightweight state container. Provider instances are owned by the agent,
    not the session. The session only holds session IDs and a mutable state dict.
    """

    def __init__(self, *, session_id: str | None = None):
        self._session_id = session_id or str(uuid.uuid4())
        self.service_session_id: str | None = None
        self.state: dict[str, Any] = {}

    @property
    def session_id(self) -> str:
        return self._session_id
```

### ChatAgent Integration

```python
class ChatAgent:
    def __init__(
        self,
        chat_client: ...,
        *,
        context_providers: Sequence[ContextProvider] | None = None,
    ):
        self._context_providers = list(context_providers or [])

    def create_session(self, *, session_id: str | None = None, service_session_id: str | None = None) -> AgentSession:
        """Create a new lightweight session."""
        session = AgentSession(session_id=session_id)
        session.service_session_id = service_session_id
        return session

    async def run(self, input: str, *, session: AgentSession) -> AgentResponse:
        context = SessionContext(session_id=session.session_id, input_messages=[...])

        # Before-run providers (forward order)
        for provider in self._context_providers:
            await provider.before_run(self, session, context, session.state)

        # ... assemble messages, invoke model ...

        # After-run providers (reverse order)
        for provider in reversed(self._context_providers):
            await provider.after_run(self, session, context, session.state)
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

# Getting all messages in provider execution order
all_messages = context.get_all_messages()

# Filtering by source
memory_messages = context.get_messages(sources=["memory"])
non_rag_messages = context.get_messages(exclude_sources=["rag"])

# Direct access to check specific sources
if "memory" in context.context_messages:
    history = context.context_messages["memory"]
```

---

## User Experience Examples

### Example 0: Zero-Config Default (Simplest Use Case)

```python
from agent_framework import ChatAgent

# No providers configured - but conversation history still works!
agent = ChatAgent(
    chat_client=client,
    name="assistant",
    # No context_providers specified
)

# Create session - automatically gets InMemoryHistoryProvider on first run
session = agent.create_session()
response = await agent.run("Hello, my name is Alice!", session=session)

# Conversation history is preserved automatically
response = await agent.run("What's my name?", session=session)
# Agent remembers: "Your name is Alice!"

# With service-managed session - no default storage added (service handles it)
service_session = agent.create_session(service_session_id="thread_abc123")

# With store=True in options - user expects service storage, no default added
response = await agent.run("Hello!", session=session, options={"store": True})
```

### Example 1: Explicit Memory Storage

```python
from agent_framework import ChatAgent
from agent_framework.context import InMemoryHistoryProvider

# Explicit provider configuration (same behavior as default, but explicit)
agent = ChatAgent(
    chat_client=client,
    name="assistant",
    context_providers=[
        InMemoryHistoryProvider(source_id="memory")
    ]
)

# Create session and chat
session = agent.create_session()
response = await agent.run("Hello!", session=session)

# Messages are automatically stored and loaded on next invocation
response = await agent.run("What did I say before?", session=session)
```

### Example 2: RAG + Memory + Audit (All HistoryProvider)

```python
from agent_framework import ChatAgent
from agent_framework.azure import CosmosHistoryProvider, AzureAISearchContextProvider
from agent_framework.redis import RedisHistoryProvider

# RAG provider that injects relevant documents
search_provider = AzureAISearchContextProvider(
    source_id="rag",
    endpoint="https://...",
    index_name="documents",
)

# Primary memory storage (loads + stores)
# load_messages=True (default) - loads and stores messages
memory_provider = RedisHistoryProvider(
    source_id="memory",
    redis_url="redis://...",
)

# Audit storage - SAME CLASS, different configuration
# load_messages=False = never loads, just stores for audit
audit_provider = CosmosHistoryProvider(
    source_id="audit",
    connection_string="...",
    load_messages=False,  # Don't load - just store for audit
)

agent = ChatAgent(
    chat_client=client,
    name="assistant",
    context_providers=[
        memory_provider,   # First: loads history
        search_provider,   # Second: adds RAG context
        audit_provider,    # Third: stores for audit (no load)
    ]
)
```

### Example 3: Custom Context Providers

```python
from agent_framework.context import ContextProvider, SessionContext

class TimeContextProvider(ContextProvider):
    """Adds current time to the context."""

    async def before_run(self, agent, session, context, state) -> None:
        from datetime import datetime
        context.add_instructions(
            self.source_id,
            f"Current date and time: {datetime.now().isoformat()}"
        )


class UserPreferencesProvider(ContextProvider):
    """Tracks and applies user preferences from conversation."""

    async def before_run(self, agent, session, context, state) -> None:
        prefs = state.get(self.source_id, {}).get("preferences", {})
        if prefs:
            context.add_instructions(
                self.source_id,
                f"User preferences: {json.dumps(prefs)}"
            )

    async def after_run(self, agent, session, context, state) -> None:
        # Extract preferences from response and store in session state
        for msg in context.response_messages or []:
            if "preference:" in msg.text.lower():
                my_state = state.setdefault(self.source_id, {})
                my_state.setdefault("preferences", {})
                # ... extract and store preference


# Compose providers - each with mandatory source_id
agent = ChatAgent(
    chat_client=client,
    context_providers=[
        InMemoryHistoryProvider(source_id="memory"),
        TimeContextProvider(source_id="time"),
        UserPreferencesProvider(source_id="prefs"),
    ]
)
```

### Example 4: Filtering by Source (Using Dict-Based Context)

```python
class SelectiveContextProvider(ContextProvider):
    """Provider that only processes messages from specific sources."""

    async def before_run(self, agent, session, context, state) -> None:
        # Check what sources have added messages so far
        print(f"Sources so far: {list(context.context_messages.keys())}")

        # Get messages excluding RAG context
        non_rag_messages = context.get_messages(exclude_sources=["rag"])

        # Or get only memory messages
        if "memory" in context.context_messages:
            memory_only = context.context_messages["memory"]

        # Do something with filtered messages...
        # e.g., sentiment analysis, topic extraction


class RAGContextProvider(ContextProvider):
    """Provider that adds RAG context."""

    async def before_run(self, agent, session, context, state) -> None:
        # Search for relevant documents based on input
        relevant_docs = await self._search(context.input_messages)

        # Add RAG context using explicit method
        rag_messages = [
            ChatMessage(role="system", text=f"Relevant info: {doc}")
            for doc in relevant_docs
        ]
        context.add_messages(self.source_id, rag_messages)
```

### Example 5: Explicit Storage Configuration for Service-Managed Sessions

```python
# HistoryProvider uses explicit configuration - no automatic detection.
# load_messages=True (default): Load messages from storage
# load_messages=False: Skip loading (useful for audit-only storage)

agent = ChatAgent(
    chat_client=client,
    context_providers=[
        RedisHistoryProvider(
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
service_storage = RedisHistoryProvider(
    source_id="audit",
    redis_url="redis://...",
    load_messages=False,  # Don't load - service manages history
)

agent_with_service = ChatAgent(
    chat_client=client,
    context_providers=[service_storage]
)
service_session = agent_with_service.create_session(service_session_id="thread_abc123")
response = await agent_with_service.run("Hello!", session=service_session)
# History provider stores for audit but doesn't load (service handles history)
```

### Example 6: Multiple Instances of Same Provider Type

```python
# You can have multiple instances of the same provider class
# by using different source_ids

agent = ChatAgent(
    chat_client=client,
    context_providers=[
        # Primary storage for conversation history
        RedisHistoryProvider(
            source_id="conversation_memory",
            redis_url="redis://primary...",
            load_messages=True,  # This one loads
        ),
        # Secondary storage for audit (different Redis instance)
        RedisHistoryProvider(
            source_id="audit_log",
            redis_url="redis://audit...",
            load_messages=False,  # This one just stores
        ),
    ]
)
# Warning will NOT be logged because only one has load_messages=True
```

### Example 7: Provider Ordering - RAG Before vs After Memory

The order of providers determines what context each one can see. This is especially important for RAG, which may benefit from seeing conversation history.

```python
from agent_framework import ChatAgent
from agent_framework.context import InMemoryHistoryProvider, ContextProvider, SessionContext

class RAGContextProvider(ContextProvider):
    """RAG provider that retrieves relevant documents based on available context."""

    async def before_run(self, agent, session, context, state) -> None:
        # Build query from what we can see
        query_parts = []

        # We can always see the current input
        for msg in context.input_messages:
            query_parts.append(msg.text)

        # Can we see history? Depends on provider order!
        history = context.get_all_messages()  # Gets context from providers that ran before us
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
    context_providers=[
        RAGContextProvider("rag"),           # Runs first - only sees input_messages
        InMemoryHistoryProvider("memory"),   # Runs second - loads/stores history
    ]
)

# Flow:
# 1. RAG.before_run():
#    - context.input_messages = ["What's the weather?"]
#    - context.get_all_messages() = []  (empty - memory hasn't run yet)
#    - RAG query based on: "What's the weather?" only
#    - Adds: context_messages["rag"] = [retrieved docs]
#
# 2. Memory.before_run():
#    - Loads history: context_messages["memory"] = [previous conversation]
#
# 3. Agent invocation with: history + rag docs + input
#
# 4. Memory.after_run():
#    - Stores: input + response (not RAG docs by default)
#
# 5. RAG.after_run():
#    - (nothing to do)


# =============================================================================
# SCENARIO B: RAG runs AFTER Memory
# =============================================================================
# RAG sees conversation history - can use it for better retrieval
# Use when: RAG should consider conversation context for better results

agent_memory_first = ChatAgent(
    chat_client=client,
    context_providers=[
        InMemoryHistoryProvider("memory"),   # Runs first - loads history
        RAGContextProvider("rag"),           # Runs second - sees history + input
    ]
)

# Flow:
# 1. Memory.before_run():
#    - Loads history: context_messages["memory"] = [previous conversation]
#
# 2. RAG.before_run():
#    - context.input_messages = ["What's the weather?"]
#    - context.get_all_messages() = [previous conversation]  (sees history!)
#    - RAG query based on: recent history + "What's the weather?"
#    - Better retrieval because RAG understands conversation context
#    - Adds: context_messages["rag"] = [more relevant docs]
#
# 3. Agent invocation with: history + rag docs + input
#
# 4. RAG.after_run():
#    - (nothing to do)
#
# 5. Memory.after_run():
#    - Stores: input + response


# =============================================================================
# SCENARIO C: RAG after Memory, with selective storage
# =============================================================================
# Memory first for better RAG, plus separate audit that stores RAG context

agent_full_context = ChatAgent(
    chat_client=client,
    context_providers=[
        InMemoryHistoryProvider("memory"),   # Primary history storage
        RAGContextProvider("rag"),           # Gets history context for better retrieval
        PersonaContextProvider("persona"),   # Adds persona instructions
        # Audit storage - stores everything including RAG results
        CosmosHistoryProvider(
            "audit",
            load_messages=False,               # Don't load (memory handles that)
            store_context_messages=True,       # Store RAG + persona context too
        ),
    ]
)
```

---

### Workplan

The implementation is split into 2 PRs to limit scope and simplify review.

```
PR1 (New Types) ──► PR2 (Agent Integration + Cleanup)
```

#### PR 1: New Types

**Goal:** Create all new types. No changes to existing code yet.

**Core Package - `packages/core/agent_framework/_sessions.py`:**
- [ ] `SessionContext` class with explicit add/get methods
- [ ] `ContextProvider` base class with `before_run()`/`after_run()`
- [ ] `HistoryProvider` derived class with load_messages/store flags
- [ ] Add `serialize()` and `restore()` methods to `ContextProvider` base class
- [ ] `AgentSession` class with `state: dict[str, Any]`
- [ ] `InMemoryHistoryProvider(HistoryProvider)`

**External Packages:**
- [ ] `packages/azure-ai-search/` - create `AzureAISearchContextProvider`
- [ ] `packages/redis/` - create `RedisHistoryProvider`
- [ ] `packages/mem0/` - create `Mem0ContextProvider`

**Testing:**
- [ ] Unit tests for `SessionContext` methods (add_messages, get_messages, add_instructions, add_tools)
- [ ] Unit tests for `HistoryProvider` load/store flags
- [ ] Unit tests for `InMemoryHistoryProvider` serialize/restore
- [ ] Unit tests for source attribution (mandatory source_id)

---

#### PR 2: Agent Integration + Cleanup

**Goal:** Wire up new types into `ChatAgent` and remove old types.

**Changes to `ChatAgent`:**
- [ ] Replace `thread` parameter with `session` in `agent.run()`
- [ ] Add `context_providers` parameter to `ChatAgent.__init__()`
- [ ] Add `create_session()` method
- [ ] Add `serialize_session()` / `restore_session()` methods
- [ ] Wire up provider iteration (before_run forward, after_run reverse)
- [ ] Add validation warning if multiple/zero history providers have `load_messages=True`
- [ ] Wire up default `InMemoryHistoryProvider` behavior (auto-add when no providers and no service_session_id)

**Remove Legacy Types:**
- [ ] `packages/core/agent_framework/_memory.py` - remove `ContextProvider` class
- [ ] `packages/core/agent_framework/_threads.py` - remove `ChatMessageStore`, `ChatMessageStoreProtocol`, `AgentThread`
- [ ] `packages/core/agent_framework/__init__.py` - remove old exports, add new exports from `_sessions.py`
- [ ] Remove old provider classes from `azure-ai-search`, `redis`, `mem0`

**Documentation & Samples:**
- [ ] Update all samples in `samples/` to use new API
- [ ] Write migration guide
- [ ] Update API documentation

**Testing:**
- [ ] Unit tests for provider execution order (before_run forward, after_run reverse)
- [ ] Unit tests for validation warnings (multiple/zero loaders)
- [ ] Unit tests for session serialization/deserialization
- [ ] Integration test: agent with `context_providers` + `session` works
- [ ] Integration test: full conversation with memory persistence
- [ ] Ensure all existing tests still pass (with updated API)
- [ ] Verify no references to removed types remain

---

#### CHANGELOG (single entry for release)

- **[BREAKING]** Replaced `ContextProvider` with new `ContextProvider` (hooks pattern with `before_run`/`after_run`)
- **[BREAKING]** Replaced `ChatMessageStore` with `HistoryProvider`
- **[BREAKING]** Replaced `AgentThread` with `AgentSession`
- **[BREAKING]** Replaced `thread` parameter with `session` in `agent.run()`
- Added `SessionContext` for invocation state with source attribution
- Added `InMemoryHistoryProvider` for conversation history
- Added session serialization (`serialize_session`, `restore_session`)

---

#### Estimated Sizes

| PR | New Lines | Modified Lines | Risk |
|----|-----------|----------------|------|
| PR1 | ~500 | ~0 | Low |
| PR2 | ~150 | ~400 | Medium |

---

#### Reference Implementation

Full implementation code for the chosen design (hooks pattern, Decision B1).

##### SessionContext

```python
# Copyright (c) Microsoft. All rights reserved.

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from ._types import ChatMessage
from ._tools import ToolProtocol


class SessionContext:
    """Per-invocation state passed through the context provider pipeline.

    Created fresh for each agent.run() call. Providers read from and write to
    the mutable fields to add context before invocation and process responses after.

    Attributes:
        session_id: The ID of the current session
        service_session_id: Service-managed session ID (if present, service handles storage)
        input_messages: The new messages being sent to the agent (read-only, set by caller)
        context_messages: Dict mapping source_id -> messages added by that provider.
            Maintains insertion order (provider execution order). Use add_messages()
            to add messages with proper source attribution.
        instructions: Additional instructions - providers can append here
        tools: Additional tools - providers can append here
        response_messages: After invocation, contains the agent's response (set by agent).
            READ-ONLY - modifications are ignored. Use AgentMiddleware to modify responses.
        options: Options passed to agent.run() - READ-ONLY, for reflection only
        metadata: Shared metadata dictionary for cross-provider communication

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

    def add_messages(self, source_id: str, messages: Sequence[ChatMessage]) -> None:
        """Add context messages from a specific source.

        Messages are stored keyed by source_id, maintaining insertion order
        based on provider execution order.

        Args:
            source_id: The provider source_id adding these messages
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
            source_id: The provider source_id adding these instructions
            instructions: A single instruction string or sequence of strings
        """
        if isinstance(instructions, str):
            instructions = [instructions]
        self.instructions.extend(instructions)

    def add_tools(self, source_id: str, tools: Sequence[ToolProtocol]) -> None:
        """Add tools to be available for this invocation.

        Tools are added with source attribution in their metadata.

        Args:
            source_id: The provider source_id adding these tools
            tools: The tools to add
        """
        for tool in tools:
            if hasattr(tool, 'metadata') and isinstance(tool.metadata, dict):
                tool.metadata["context_source"] = source_id
        self.tools.extend(tools)

    def get_messages(
        self,
        sources: Sequence[str] | None = None,
        exclude_sources: Sequence[str] | None = None,
    ) -> list[ChatMessage]:
        """Get context messages, optionally filtered by source.

        Returns messages in provider execution order (dict insertion order).

        Args:
            sources: If provided, only include messages from these sources
            exclude_sources: If provided, exclude messages from these sources

        Returns:
            Flattened list of messages in provider execution order
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
        1. Context messages (from providers, in execution order)
        2. Input messages (if include_input=True)
        3. Response messages (if include_response=True)

        Args:
            include_input: If True, append input_messages after context
            include_response: If True, append response_messages at the end

        Returns:
            Flattened list of messages in conversation order
        """
        result: list[ChatMessage] = []
        for messages in self.context_messages.values():
            result.extend(messages)
        if include_input and self.input_messages:
            result.extend(self.input_messages)
        if include_response and self.response_messages:
            result.extend(self.response_messages)
        return result
```

##### ContextProvider

```python
class ContextProvider(ABC):
    """Base class for context providers (hooks pattern).

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
                Used for message/tool attribution.
        """
        self.source_id = source_id

    async def before_run(
        self,
        agent: "ChatAgent",
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Called before model invocation.

        Override to add context (messages, instructions, tools) to the
        SessionContext before the model is invoked.

        Args:
            agent: The agent running this invocation
            session: The current session
            context: The invocation context - add messages/instructions/tools here
            state: The session's mutable state dict
        """
        pass

    async def after_run(
        self,
        agent: "ChatAgent",
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Called after model invocation.

        Override to process the response (store messages, extract info, etc.).
        The context.response_messages will be populated at this point.

        Args:
            agent: The agent that ran this invocation
            session: The current session
            context: The invocation context with response_messages populated
            state: The session's mutable state dict
        """
        pass

    async def serialize(self) -> Any:
        """Serialize provider state. Default returns None (no state)."""
        return None

    async def restore(self, state: Any) -> None:
        """Restore provider state from serialized object."""
        pass
```

##### HistoryProvider

```python
class HistoryProvider(ContextProvider):
    """Base class for conversation history storage providers.

    A single class that can be configured for different use cases:
    - Primary memory storage (loads + stores messages)
    - Audit/logging storage (stores only, doesn't load)
    - Evaluation storage (stores only for later analysis)

    Loading behavior (when to add messages to context_messages[source_id]):
    - `load_messages=True` (default): Load messages from storage
    - `load_messages=False`: Skip loading (before_run is a no-op)

    Storage behavior:
    - `store_inputs`: Store input messages (default True)
    - `store_responses`: Store response messages (default True)
    - Storage always happens unless explicitly disabled, regardless of load_messages

    Warning: At session creation time, a warning is logged if:
    - Multiple history providers have `load_messages=True` (likely duplicate loading)
    - Zero history providers have `load_messages=True` (likely missing primary storage)

    Examples:
        # Primary memory - loads and stores
        memory = InMemoryHistoryProvider(source_id="memory")

        # Audit storage - stores only, doesn't add to context
        audit = RedisHistoryProvider(
            source_id="audit",
            load_messages=False,
            redis_url="redis://...",
        )

        # Full audit - stores everything including RAG context
        full_audit = CosmosHistoryProvider(
            source_id="full_audit",
            load_messages=False,
            store_context_messages=True,
        )
    """

    def __init__(
        self,
        source_id: str,
        *,
        load_messages: bool = True,
        store_responses: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: Sequence[str] | None = None,
    ):
        super().__init__(source_id)
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
            return context.get_messages(sources=self.store_context_from)
        else:
            return context.get_messages(exclude_sources=[self.source_id])

    async def before_run(self, agent, session, context, state) -> None:
        """Load history into context if configured."""
        if self.load_messages:
            history = await self.get_messages(context.session_id)
            context.add_messages(self.source_id, history)

    async def after_run(self, agent, session, context, state) -> None:
        """Store messages based on configuration."""
        messages_to_store: list[ChatMessage] = []
        messages_to_store.extend(self._get_context_messages_to_store(context))
        if self.store_inputs:
            messages_to_store.extend(context.input_messages)
        if self.store_responses and context.response_messages:
            messages_to_store.extend(context.response_messages)
        if messages_to_store:
            await self.save_messages(context.session_id, messages_to_store)
```

##### AgentSession

```python
import uuid
import warnings
from collections.abc import Sequence


class AgentSession:
    """A conversation session with an agent.

    Lightweight state container. Provider instances are owned by the agent,
    not the session. The session only holds session IDs and a mutable state dict.

    Attributes:
        session_id: Unique identifier for this session
        service_session_id: Service-managed session ID (if using service-side storage)
        state: Mutable state dict shared with all providers
    """

    def __init__(
        self,
        *,
        session_id: str | None = None,
        service_session_id: str | None = None,
    ):
        """Initialize the session.

        Note: Prefer using agent.create_session() instead of direct construction.

        Args:
            session_id: Optional session ID (generated if not provided)
            service_session_id: Optional service-managed session ID
        """
        self._session_id = session_id or str(uuid.uuid4())
        self.service_session_id = service_session_id
        self.state: dict[str, Any] = {}

    @property
    def session_id(self) -> str:
        """The unique identifier for this session."""
        return self._session_id


# Example of how agent creates sessions and runs providers:
class ChatAgent:
    def __init__(
        self,
        chat_client: ...,
        *,
        context_providers: Sequence[ContextProvider] | None = None,
    ):
        self._context_providers = list(context_providers or [])

    def create_session(
        self,
        *,
        session_id: str | None = None,
        service_session_id: str | None = None,
    ) -> AgentSession:
        """Create a new lightweight session.

        Args:
            session_id: Optional session ID (generated if not provided)
            service_session_id: Optional service-managed session ID
        """
        return AgentSession(
            session_id=session_id,
            service_session_id=service_session_id,
        )

    def _ensure_default_storage(self, session: AgentSession, options: dict[str, Any]) -> None:
        """Add default InMemoryHistoryProvider if needed.

        Default storage is added when ALL of these are true:
        - No service_session_id (service not managing storage)
        - options.store is not True (user not expecting service storage)
        - No context_providers configured at all
        """
        if options.get("store") is True:
            return
        if session.service_session_id is not None:
            return
        if self._context_providers:
            return
        # Add default in-memory storage
        self._context_providers.append(InMemoryHistoryProvider("memory"))

    def _validate_providers(self) -> None:
        """Warn if history provider configuration looks like a mistake."""
        storage_providers = [
            p for p in self._context_providers
            if isinstance(p, HistoryProvider)
        ]
        if not storage_providers:
            return
        loaders = [p for p in storage_providers if p.load_messages is True]
        if len(loaders) > 1:
            warnings.warn(
                f"Multiple history providers configured to load messages: "
                f"{[p.source_id for p in loaders]}. "
                f"This may cause duplicate messages in context.",
                UserWarning
            )
        elif len(loaders) == 0:
            warnings.warn(
                f"History providers configured but none have load_messages=True: "
                f"{[p.source_id for p in storage_providers]}. "
                f"No conversation history will be loaded.",
                UserWarning
            )

    async def run(self, input: str, *, session: AgentSession, options: dict[str, Any] | None = None) -> ...:
        """Run the agent with the given input."""
        options = options or {}

        # Ensure default storage on first run
        self._ensure_default_storage(session, options)
        self._validate_providers()

        context = SessionContext(
            session_id=session.session_id,
            service_session_id=session.service_session_id,
            input_messages=[...],
            options=options,
        )

        # Before-run providers (forward order)
        for provider in self._context_providers:
            await provider.before_run(self, session, context, session.state)

        # ... assemble final messages from context, invoke model ...

        # After-run providers (reverse order)
        for provider in reversed(self._context_providers):
            await provider.after_run(self, session, context, session.state)

    async def serialize_session(self, session: AgentSession) -> dict[str, Any]:
        """Serialize a session's state for persistence."""
        provider_states: dict[str, Any] = {}
        for provider in self._context_providers:
            state = await provider.serialize()
            if state is not None:
                provider_states[provider.source_id] = state
        return {
            "session_id": session.session_id,
            "service_session_id": session.service_session_id,
            "state": session.state,
            "provider_states": provider_states,
        }

    async def restore_session(self, serialized: dict[str, Any]) -> AgentSession:
        """Restore a session from serialized state."""
        session = AgentSession(
            session_id=serialized["session_id"],
            service_session_id=serialized.get("service_session_id"),
        )
        session.state = serialized.get("state", {})
        provider_states = serialized.get("provider_states", {})
        for provider in self._context_providers:
            if provider.source_id in provider_states:
                await provider.restore(provider_states[provider.source_id])
        return session
```
