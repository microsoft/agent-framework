---
status: proposed
contact: eavanvalkenburg
date: 2026-02-10
deciders: eavanvalkenburg, markwallace-microsoft, sphenry, alliscode, johanst, brettcannon, westey-m
consulted: taochenosu, moonbox3, dmytrostruk, giles17
---

# Context Compaction Strategy for Long-Running Agents

## Context and Problem Statement

Long-running agents need **context compaction** — automatically summarizing or truncating conversation history when approaching token limits. This is particularly important for agents that make many tool calls in succession (10s or 100s), where the context can grow unboundedly.

[ADR-0016](0016-python-context-middleware.md) established the `ContextProvider` (hooks pattern) and `HistoryProvider` architecture for session management and context engineering. The .NET SDK comparison table notes:

> **Message reduction**: `IChatReducer` on `InMemoryChatHistoryProvider` → Not yet designed (see Open Discussion: Context Compaction)

This ADR proposes a design for context compaction that integrates with the chosen architecture.

### Why Current Architecture Cannot Support In-Run Compaction

An [analysis of the current message flow](https://gist.github.com/victordibia/ec3f3baf97345f7e47da025cf55b999f) identified three structural barriers to implementing compaction inside the tool loop:

1. **History loaded once**: `HistoryProvider.get_messages()` is only called once during `before_run` at the start of `agent.run()`. The tool loop maintains its own message list internally and never re-reads from the provider.

2. **`ChatMiddleware` modifies copies**: `ChatMiddleware` receives a **copy** of the message list each iteration. Clearing/replacing `context.messages` in middleware only affects that single LLM call — the tool loop's internal message list keeps growing with each tool result.

3. **`FunctionMiddleware` wraps tool calls, not LLM calls**: `FunctionMiddleware` runs around individual tool executions, not around the LLM call that triggers them. It cannot modify the message history between iterations.

```
agent.run(task)
  │
  ├── ContextProvider.before_run()          ← Load history, inject context ONCE
  │
  ├── chat_client.get_response(messages)
  │     │
  │     ├── messages = copy(messages)        ← NEW list created
  │     │
  │     └── for attempt in range(max_iterations):          ← TOOL LOOP
  │           ├── ChatMiddleware(copy of messages)          ← Modifies copy only
  │           ├── LLM call(messages)                        ← Response may contain tool_calls
  │           ├── FunctionMiddleware(tool_call)              ← Wraps each tool execution
  │           │     └── Execute single tool call
  │           └── messages.extend(tool_results)             ← List grows unbounded
  │
  └── ContextProvider.after_run()           ← Store messages ONCE
```

**Consequence**: There is currently **no way** to compact messages during the tool loop such that subsequent LLM calls use the reduced context. Any middleware-based approach only affects individual LLM calls but the underlying list keeps growing.

### Where Compaction Is Needed

Compaction must be applicable in **four distinct points** in the agent lifecycle:

| Point | When | Purpose |
|-------|------|---------|
| **Post-load** | After `HistoryProvider.get_messages()` returns in `before_run` | Compact history before sending to the model, while keeping the full history in storage |
| **Pre-write** | Before `HistoryProvider.save_messages()` in `after_run` | Compact before persisting to storage, limiting storage size |
| **In-run (tool loop)** | During function calling loops within a single `agent.run()` | Keep context within limits as tool calls accumulate |
| **On existing storage** | Outside of `agent.run()`, as a maintenance operation | Compact stored history (e.g., cron job, manual trigger) |

### Scope: Not Applicable to Service-Managed Storage

**All compaction discussed in this ADR is irrelevant when using only service-managed storage** (`service_session_id` is set). In that scenario:
- The service manages message history internally — the client never holds the full conversation
- Only new messages are sent to/from the service each turn
- The service is responsible for its own context window management and compaction
- The client has no message list to compact

This ADR applies to two scenarios where the **client** constructs and manages the message list sent to the model:

1. **With local storage** (e.g., `InMemoryHistoryProvider`, Redis, Cosmos) — compaction is needed at all four points (post-load, pre-write, in-run, existing storage)
2. **Without any storage** (`store=False`, no `HistoryProvider`) — in-run compaction is still critical for long-running, tool-heavy agent invocations where the message list grows unbounded within a single `agent.run()` call

### Compaction Strategies (Examples)

A compaction strategy takes a list of messages and returns a (potentially shorter) list:

- **Truncation**: Keep only the last N messages or N tokens
- **Summarization**: Replace older messages with an LLM-generated summary
- **Selective removal**: Remove tool call/result pairs while keeping user/assistant turns
- **Sliding window with anchor**: Keep system message + last N messages
- **Token budget**: Remove oldest messages until under a token threshold

### Atomic Group Preservation

A critical constraint for any compaction strategy: **tool calls and their results must be kept together**. LLM APIs (OpenAI, Azure, etc.) require that an assistant message containing `tool_calls` is always followed by corresponding `tool` result messages. A compaction strategy that removes one without the other will cause API errors.

Strategies must treat `[assistant message with tool_calls] + [tool result messages]` as atomic groups — either keep the entire group or remove it entirely.

### Leveraging Source Attribution

ADR-0016 introduces `source_id` attribution on messages — each message tracks which `ContextProvider` added it. Compaction strategies can use this attribution to make informed decisions about what to compact and what to preserve:

- **Preserve RAG context**: Messages from a RAG provider (`source_id: "rag"`) may be critical and should survive compaction
- **Remove ephemeral context**: Messages marked as ephemeral (e.g., `source_id: "time"`) can be safely removed
- **Protect user input**: Messages without a `source_id` (direct user input) should typically be preserved
- **Selective tool result compaction**: Tool results from specific providers can be summarized while others are kept verbatim

This means strategies don't need to rely solely on message position or role — they can make semantically meaningful compaction decisions based on the origin of each message.

### `HistoryProvider.save_messages` Is Append-Only

ADR-0016's `HistoryProvider.save_messages()` is an **append** operation — `after_run` collects the new messages from the current invocation and appends them to storage. There is no built-in way to **replace** the full stored history with a compacted version.

For compaction on existing storage (and pre-write compaction that rewrites history), we need a way to overwrite rather than append. Two options:

1. **Add a `replace_messages()` method** to `HistoryProvider`:

```python
class HistoryProvider(ContextProvider):
    @abstractmethod
    async def save_messages(self, session_id: str | None, messages: Sequence[ChatMessage]) -> None:
        """Append messages to storage for this session."""
        ...

    async def replace_messages(self, session_id: str | None, messages: Sequence[ChatMessage]) -> None:
        """Replace all stored messages for this session. Used for compaction.

        Default implementation raises NotImplementedError. Providers that support
        compaction on existing storage must override this method.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support replace_messages. "
            "Override this method to enable storage compaction."
        )
```

2. **Add a `mode` parameter** to `save_messages()`:

```python
class HistoryProvider(ContextProvider):
    @abstractmethod
    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[ChatMessage],
        *,
        overwrite: bool = False,
    ) -> None:
        """Persist messages for this session.

        Args:
            overwrite: If True, replace all existing messages instead of appending.
                       Used for compaction workflows.
        """
        ...
```

Either approach enables the compaction-on-existing-storage workflow:

```python
history = await provider.get_messages(session_id)
compacted = await strategy.compact(history)
await provider.replace_messages(session_id, compacted)  # Option 1
# or
await provider.save_messages(session_id, compacted, overwrite=True)  # Option 2
```

This design choice is orthogonal to the compaction strategy options below — any option requires one of these `HistoryProvider` extensions.

## Decision Drivers

- **Applicable everywhere**: The same strategy object must work at post-load, pre-write, in-run (tool loop), and on existing storage
- **Composable with HistoryProvider**: Works naturally with the `HistoryProvider` subclass from ADR-0016
- **Composable with function calling**: Can be applied during the tool loop without requiring `ContextProvider` to run mid-loop
- **Cross-platform consistency**: The .NET SDK uses `IChatReducer` on `InMemoryChatHistoryProvider` with a `ChatReducerTriggerEvent` enum
- **Attribution-aware**: Can leverage `source_id` attribution on messages to make informed compaction decisions (e.g., preserve RAG context, remove ephemeral messages)

## Considered Options

- Standalone `CompactionStrategy` object composed into `HistoryProvider` and `FunctionInvocationConfiguration`
- `CompactionStrategy` as a mixin for `HistoryProvider` subclasses
- Separate `CompactionProvider` set directly on the agent
- Mutable message access in `ChatMiddleware`


## Pros and Cons of the Options

### Option 1: Standalone `CompactionStrategy` Object

Define an abstract `CompactionStrategy` (or `ChatReducer` for .NET alignment) that can be **composed into any `HistoryProvider`** and also passed to the agent for in-run compaction.

```python
class CompactionStrategy(ABC):
    """Abstract strategy for compacting a list of messages."""

    @abstractmethod
    async def compact(self, messages: Sequence[ChatMessage]) -> list[ChatMessage]:
        """Reduce a list of messages. Returns the compacted list."""
        ...
```

**Usage with `HistoryProvider`:**

```python
class HistoryProvider(ContextProvider):
    def __init__(
        self,
        source_id: str,
        *,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_responses: bool = True,
        # NEW: optional compaction strategies
        post_load_compaction: CompactionStrategy | None = None,
        pre_write_compaction: CompactionStrategy | None = None,
    ): ...

    async def before_run(self, agent, session, context, state) -> None:
        history = await self.get_messages(context.session_id)
        if self.post_load_compaction:
            history = await self.post_load_compaction.compact(history)
        context.extend_messages(self.source_id, history)

    async def after_run(self, agent, session, context, state) -> None:
        messages_to_store = self._collect_messages(context)
        if self.pre_write_compaction:
            messages_to_store = await self.pre_write_compaction.compact(messages_to_store)
        if messages_to_store:
            await self.save_messages(context.session_id, messages_to_store)
```

**Usage for in-run compaction (tool loop):**

In-run compaction is configured via `FunctionInvocationConfiguration`, the existing TypedDict that controls the function calling loop (max iterations, error handling, etc.). Adding a `compaction_strategy` field keeps all loop-related configuration in one place:

```python
class FunctionInvocationConfiguration(TypedDict, total=False):
    enabled: bool
    max_iterations: int
    max_consecutive_errors_per_request: int
    terminate_on_unknown_calls: bool
    additional_tools: Sequence[ToolProtocol]
    include_detailed_errors: bool
    compaction_strategy: CompactionStrategy | None  # NEW
```

During the function calling loop, after each tool result is appended, the strategy is applied:

```python
# Inside the function invocation loop (e.g., in _try_execute_function_calls)
messages.append(tool_result_message)
if config.get("compaction_strategy"):
    messages = await config["compaction_strategy"].compact(messages)
```

This means the same `CompactionStrategy` object can be reused across `HistoryProvider` (boundary compaction) and `FunctionInvocationConfiguration` (in-run compaction):

```python
strategy = SlidingWindowStrategy(max_messages=100)

agent = chat_client.create_agent(
    context_providers=[
        InMemoryHistoryProvider("memory", post_load_compaction=strategy),
    ],
    function_invocation_configuration={
        "max_iterations": 40,
        "compaction_strategy": strategy,  # Same strategy for tool loop
    },
)
```

**Usage on existing storage (maintenance):**

```python
# Compact stored history outside of agent.run()
strategy = SlidingWindowStrategy(max_messages=100)
history = await my_history_provider.get_messages(session_id)
compacted = await strategy.compact(history)
await my_history_provider.save_messages(session_id, compacted)
```

**Built-in strategies:**

```python
class TruncationStrategy(CompactionStrategy):
    """Keep the last N messages, optionally preserving the system message."""
    def __init__(self, max_messages: int, preserve_system: bool = True): ...

class SlidingWindowStrategy(CompactionStrategy):
    """Keep system message + last N messages."""
    def __init__(self, max_messages: int): ...

class SummarizationStrategy(CompactionStrategy):
    """Summarize older messages using an LLM."""
    def __init__(self, chat_client: ..., max_messages_before_summary: int): ...
```

- Good, because the same strategy object works at all four compaction points (post-load, pre-write, in-run, existing storage)
- Good, because strategies are fully reusable — one instance can be shared across providers and agents
- Good, because it follows the Strategy pattern, a well-understood design pattern
- Good, because new strategies can be added without modifying `HistoryProvider`
- Good, because the `compact()` method signature (`messages -> messages`) aligns with .NET's `IChatReducer.ReduceAsync()`
- Good, because it is easy to test strategies in isolation
- Good, because strategies can inspect `source_id` attribution on messages for informed decisions
- Good, because in-run compaction fits naturally into `FunctionInvocationConfiguration`, keeping all loop settings together
- Bad, because it adds a new concept (`CompactionStrategy`) alongside the existing `ContextProvider`/`HistoryProvider` hierarchy

### Option 2: `CompactionStrategy` as a Mixin for `HistoryProvider`

Define compaction behavior as a mixin that `HistoryProvider` subclasses can opt into. The mixin adds `compact()` as an overridable method.

```python
class CompactingHistoryMixin:
    """Mixin that adds compaction to a HistoryProvider."""

    async def compact(self, messages: Sequence[ChatMessage]) -> list[ChatMessage]:
        """Override to implement compaction logic. Default: no-op."""
        return list(messages)


class InMemoryHistoryProvider(CompactingHistoryMixin, HistoryProvider):
    """In-memory history with compaction support."""

    def __init__(
        self,
        source_id: str,
        *,
        max_messages: int | None = None,
        **kwargs,
    ):
        super().__init__(source_id, **kwargs)
        self.max_messages = max_messages

    async def compact(self, messages: Sequence[ChatMessage]) -> list[ChatMessage]:
        if self.max_messages and len(messages) > self.max_messages:
            return list(messages[-self.max_messages:])
        return list(messages)
```

The base `HistoryProvider` checks for the mixin and calls `compact()` at the right points:

```python
class HistoryProvider(ContextProvider):
    async def before_run(self, agent, session, context, state) -> None:
        history = await self.get_messages(context.session_id)
        if isinstance(self, CompactingHistoryMixin):
            history = await self.compact(history)
        context.extend_messages(self.source_id, history)
```

For in-run compaction, the `FunctionInvocationConfiguration` would reference the provider's `compact()` method, but this requires knowing which provider to use:

```python
# Awkward: must extract compaction from a specific provider
compacting_provider = next(
    (p for p in agent._context_providers if isinstance(p, CompactingHistoryMixin)),
    None,
)
config: FunctionInvocationConfiguration = {
    "compaction_strategy": compacting_provider,  # provider IS the strategy
}
```

For existing storage:

```python
# Provider must implement CompactingHistoryMixin
provider = InMemoryHistoryProvider("memory", max_messages=100)
history = await provider.get_messages(session_id)
compacted = await provider.compact(history)
await provider.save_messages(session_id, compacted)
```

- Good, because no new top-level concept — compaction is part of the provider
- Good, because the provider controls its own compaction logic
- Neutral, because mixins are idiomatic Python but can be harder to reason about in complex hierarchies
- Bad, because **compaction strategy is coupled to the provider** — cannot share the same strategy across different providers
- Bad, because different strategies per compaction point (post-load vs pre-write) require additional configuration or separate methods
- Bad, because in-run compaction via `FunctionInvocationConfiguration` requires extracting the mixin from the provider list — unclear which one to use if multiple exist
- Bad, because `isinstance` checks are fragile and don't compose well
- Bad, because testing compaction requires instantiating a full provider rather than testing the strategy in isolation
- Bad, because existing storage compaction requires having the right provider type, not just any strategy

### Option 3: Separate `CompactionProvider` Set on the Agent

Define compaction as a special `ContextProvider` subclass that the agent calls at all compaction points (pre-load, pre-write, in-run, existing storage). It is added to the agent's `context_providers` list like any other provider.

```python
class CompactionProvider(ContextProvider):
    """Context provider specialized for compaction.

    Unlike regular ContextProviders, CompactionProvider is also invoked
    during the function calling loop and can be used for storage maintenance.
    """

    @abstractmethod
    async def compact(self, messages: Sequence[ChatMessage]) -> list[ChatMessage]:
        """Reduce a list of messages."""
        ...

    async def before_run(self, agent, session, context, state) -> None:
        """Compact messages loaded by previous providers (post-load)."""
        all_messages = context.get_all_messages()
        compacted = await self.compact(all_messages)
        context.replace_messages(compacted)

    async def after_run(self, agent, session, context, state) -> None:
        """No-op by default. Subclasses can override for pre-write behavior."""
        pass
```

**Usage:**

```python
agent = ChatAgent(
    chat_client=client,
    context_providers=[
        InMemoryHistoryProvider("memory"),       # Loads history
        RAGContextProvider("rag"),               # Adds RAG context
        SlidingWindowCompaction("compaction", max_messages=100),  # Compacts everything
    ],
)
```

The agent recognizes `CompactionProvider` instances and wires `compact()` into `FunctionInvocationConfiguration`:

```python
class ChatAgent:
    def _build_function_config(self) -> FunctionInvocationConfiguration:
        compactors = [p for p in self._context_providers if isinstance(p, CompactionProvider)]
        strategy = compactors[0] if compactors else None  # Which one if multiple?
        return {"compaction_strategy": strategy, ...}
```

For existing storage, the `compact()` method is called directly:

```python
compactor = SlidingWindowCompaction("compaction", max_messages=100)
history = await my_history_provider.get_messages(session_id)
compacted = await compactor.compact(history)
await my_history_provider.save_messages(session_id, compacted)
```

- Good, because it lives within the existing `ContextProvider` pipeline — no new concept
- Good, because ordering relative to other providers is explicit (runs after RAG provider, etc.)
- Good, because `before_run` can compact the combined output of all prior providers (history + RAG)
- Good, because the `compact()` method works standalone for existing storage maintenance
- Bad, because the `CompactionProvider` has **dual roles** (context provider + compaction strategy), which muddies the ContextProvider contract
- Bad, because `context.replace_messages()` is a new operation that doesn't exist today and conflicts with the append-only design of `SessionContext`
- Bad, because in-run compaction still requires `isinstance` checks to wire into `FunctionInvocationConfiguration`
- Bad, because ordering sensitivity is subtle — must come after storage providers but before model invocation
- Bad, because a `CompactionProvider` as a context provider gets `before_run`/`after_run` calls even when only its `compact()` method is needed (in-run and storage maintenance)

### Option 4: Mutable Message Access in `ChatMiddleware`

Instead of introducing a new compaction abstraction, change `ChatMiddleware` so that it can **replace the actual message list** used by the tool loop, rather than modifying a copy. This makes the existing middleware pattern sufficient for in-run compaction.

**Required changes to the tool loop:**

```python
# Inside the function invocation loop
# Current: ChatMiddleware modifies a copy, tool loop keeps its own list
# Proposed: ChatMiddleware can replace the list, tool loop uses the replacement

for attempt_idx in range(max_iterations):
    context = ChatContext(messages=messages)
    response = await middleware_pipeline.process(context)

    # NEW: if middleware replaced messages, use the replacement
    messages = context.messages  # May be a new, compacted list

    messages.extend(tool_results)
```

**Usage:**

```python
@chat_middleware
async def compacting_middleware(context: ChatContext, next):
    if count_tokens(context.messages) > budget:
        compacted = compact(context.messages)
        context.messages.clear()
        context.messages.extend(compacted)  # Persists because tool loop reads back
    await next(context)

agent = chat_client.create_agent(
    middleware=[compacting_middleware],
)
```

For boundary compaction, the same middleware runs at the chat client level. For existing storage compaction, a standalone utility function is needed since middleware only runs during `agent.run()`.

- Good, because it uses the **existing `ChatMiddleware` pattern** — no new compaction concept
- Good, because middleware already runs between LLM calls in the tool loop — it just needs the mutations to stick
- Good, because users familiar with middleware get compaction "for free"
- Bad, because it requires **changing how the tool loop manages messages** — the current copy-based architecture must be rethought
- Bad, because multiple middleware could conflict when replacing messages (no coordination)
- Bad, because it does **not cover existing storage compaction** — `ChatMiddleware` only runs during `agent.run()`
- Bad, because it does **not cover pre-write compaction** — `ChatMiddleware` runs before the LLM call, not after `ContextProvider.after_run()`
- Bad, because message replacement semantics in middleware are implicit (mutating a list) rather than explicit (returning a new list)
- Bad, because it requires significant internal refactoring of the copy-based message flow in the function invocation layer


## Decision Outcome

Chosen option: "{to be decided}", because this ADR is currently proposed and awaiting team discussion.

### Consequences

- To be determined based on the chosen option.

## Comparison to .NET Implementation

The .NET SDK uses `IChatReducer` composed into `InMemoryChatHistoryProvider`:

| Aspect | .NET | Proposed Options |
|--------|------|-----------------|
| Interface | `IChatReducer` with `ReduceAsync(messages) -> messages` | `CompactionStrategy.compact(messages) -> messages` (Options 1-3) / `ChatMiddleware` mutation (Option 4) |
| Attachment | Property on `InMemoryChatHistoryProvider` | Composed into `HistoryProvider` (Option 1) / mixin (Option 2) / separate provider (Option 3) / middleware (Option 4) |
| Trigger | `ChatReducerTriggerEvent` enum: `AfterMessageAdded`, `BeforeMessagesRetrieval` | Post-load + pre-write + in-run + storage maintenance (Options 1-3) / in-run + post-load only (Option 4) |
| Scope | Only within `InMemoryChatHistoryProvider` | Applicable to any `HistoryProvider` and the tool loop (Option 1) |

Option 1's `CompactionStrategy` is the closest equivalent to .NET's `IChatReducer`, with a broader scope. Naming could be aligned: `ChatReducer` in Python to match `IChatReducer` in .NET.

### Coverage Matrix

How each option addresses the four compaction points and the current architectural limitations:

| Compaction Point | Option 1 (Strategy) | Option 2 (Mixin) | Option 3 (Provider) | Option 4 (Middleware) |
|-----------------|---------------------|-------------------|---------------------|-----------------------|
| **Post-load** | ✅ `HistoryProvider` param | ✅ `compact()` override | ✅ `before_run` | ✅ Middleware before LLM |
| **Pre-write** | ✅ `HistoryProvider` param | ⚠️ Needs extra method | ⚠️ `after_run` override | ❌ Not supported |
| **In-run (tool loop)** | ✅ `FunctionInvocationConfiguration` | ⚠️ Awkward extraction | ⚠️ `isinstance` wiring | ⚠️ Requires refactoring copy semantics |
| **Existing storage** | ✅ Standalone `compact()` | ✅ Provider's `compact()` | ✅ Standalone `compact()` | ❌ Not supported |
| **Solves copy problem** | ✅ Runs inside loop | ⚠️ Indirectly | ⚠️ Indirectly | ⚠️ Requires deep refactor |
| **New concepts** | 1 (`CompactionStrategy`) | 1 (mixin) | 0 (reuses `ContextProvider`) | 0 (reuses `ChatMiddleware`) |

## More Information

### Message Attribution and Compaction

The `source_id` attribution system from ADR-0016 enables intelligent compaction:

```python
class AttributionAwareStrategy(CompactionStrategy):
    """Example: remove ephemeral context but preserve RAG and user messages."""

    async def compact(self, messages: Sequence[ChatMessage]) -> list[ChatMessage]:
        result = []
        for msg in messages:
            source = msg.additional_properties.get("source_id")
            if source == "ephemeral":
                continue  # Remove ephemeral context
            result.append(msg)
        return result
```

### Open Questions

1. **Naming**: Should we use `CompactionStrategy`, `ChatReducer` (for .NET alignment), or `ContextReducer`?
2. **Trigger mechanism for in-run**: Should compaction run after every tool call, or only when a threshold is exceeded (e.g., token count, message count)?
3. **Async vs sync**: Should `compact()` be async (to support LLM-based summarization) or sync with an async variant?
4. **Chaining**: Should multiple strategies be chainable (e.g., summarize then truncate)?

### Related Decisions

- [ADR-0016: Unifying Context Management with ContextPlugin](0016-python-context-middleware.md) — Parent ADR that established `ContextProvider`, `HistoryProvider`, and `AgentSession` architecture.
- [Context Compaction Limitations Analysis](https://gist.github.com/victordibia/ec3f3baf97345f7e47da025cf55b999f) — Detailed analysis of why current architecture cannot support in-run compaction, with attempted solutions and their failure modes. Option 4 in this ADR corresponds to "Option A: Middleware Access to Mutable Message Source" from that analysis; Options 1-3 correspond to "Option B: Tool Loop Hook" (via `FunctionInvocationConfiguration`).
