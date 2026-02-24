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
| **Pre-write** | Before `HistoryProvider.save_messages()` in `after_run` | Compact before persisting to storage, limiting storage size, _only applies to messages from a run_ |
| **In-run (tool loop)** | During function calling loops within a single `agent.run()` | Keep context within limits as tool calls accumulate |
| **On existing storage** | Outside of `agent.run()`, as a maintenance operation | Compact stored history (e.g., cron job, manual trigger) |

### Scope: Not Applicable to Service-Managed Storage

**All compaction discussed in this ADR is irrelevant when using only service-managed storage** (`service_session_id` is set). In that scenario:
- The service manages message history internally — the client never holds the full conversation
- Only new messages are sent to/from the service each turn
- The service is responsible for its own context window management and compaction
- The client has no message list to compact

This ADR applies to two scenarios where the **client** constructs and manages the message list sent to the model:

1. **With local storage** (e.g., `InMemoryHistoryProvider`, Redis, Cosmos) — compaction is needed at all four points (post-load, pre-write, in-run, existing storage), currently no compaction is done in our abstractions.
2. **Without any storage** (`store=False`, no `HistoryProvider`) — in-run compaction is still critical for long-running, tool-heavy agent invocations where the message list grows unbounded within a single `agent.run()` call

### Compaction Strategies (Examples)

A compaction strategy takes a list of messages and returns a (potentially shorter) list, in almost all cases, there is certain logic that needs to be applied universally, such as retaining system messages, not breaking up function call and result pairs (for Responses that includes Reasoning as well, see [below](#atomic-group-preservation) for more info) as tool calls, etc. Beyond that, strategies can be as simple or complex as needed:

- **Truncation**: Keep only the last N messages or N tokens, this is a likely done as a kind of zigzag, where the history grows, then get's truncated to some value below the token limit, then grows again, etc. This can be done on a simple message count basis, a character count basis, or more complex token counting basis.
- **Summarization**: Replace older messages with an LLM-generated summary (depending on the implementation this could be done, by replacing the summarized messages, or by inserting a summary message in between and not loading messages older then the summarized ones)
- **Selective removal**: Remove tool call/result pairs while keeping user/assistant turns
- **Sliding window with anchor**: Keep system message + last N messages
- **Custom logic**: The design should be extendible so that users can implement their own strategies.

### Atomic Group Preservation

A critical constraint for any compaction strategy: **tool calls and their results must be kept together**. LLM APIs (OpenAI, Azure, etc.) require that an assistant message containing `tool_calls` is always followed by corresponding `tool` result messages. A compaction strategy that removes one without the other will cause API errors. This is extended for reasoning models, at least in the OpenAI Responses API with a Reasoning content, without it you also get failed calls.

Strategies must treat `[assistant message with tool_calls] + [tool result messages]` as atomic groups — either keep the entire group or remove it entirely. We can explore automatic grouping logic in the strategy implementation to enforce this constraint, to ensure not every strategy implementer needs to manually handle this. Option 1 Variant C (pre-grouped messages) addresses this structurally by having the framework compute `MessageGroup` objects before calling the strategy, so strategy authors never see raw message boundaries.

### Leveraging Source Attribution

[ADR-0016](./0016-python-context-middleware.md#4-source-attribution-via-source_id) introduces `source_id` attribution on messages — each message tracks which `ContextProvider` added it. Compaction strategies can use this attribution to make informed decisions about what to compact and what to preserve:

- **Preserve RAG context**: Messages from a RAG provider (e.g. `source_id: "rag"`) may be critical and should survive compaction
- **Remove ephemeral context**: Messages marked as ephemeral (e.g., `source_id: "time"`) can be safely removed
- **Protect user input**: Messages without a `source_id` (direct user input) should typically be preserved
- **Selective tool result compaction**: Tool results from specific providers can be summarized while others are kept verbatim

This means strategies don't need to rely solely on message position or role — they can make semantically meaningful compaction decisions based on the origin of each message.

### Implementation details

#### Trigger mechanism for in-run compaction

Running compaction after **every** tool call is wasteful — most iterations the context is well within limits. Instead, compaction should only trigger when a threshold is exceeded. There are several approaches to consider:

1. **Message count threshold**: Trigger when the message list exceeds N messages. Simple to implement and predictable, but message count is a poor proxy for token usage — a single tool result can contain thousands of tokens while counting as one message.

2. **Character/token count threshold**: Trigger when the estimated token count exceeds a budget. More accurate but requires a token counting mechanism (exact tokenization is model-specific and expensive; character-based heuristics like `len(text) / 4` are fast but approximate).

3. **Iteration-based**: Trigger every N tool loop iterations (e.g., every 10th iteration). Predictable cadence but doesn't account for actual context growth — 10 iterations with small results may not need compaction while 3 iterations with large results might.

4. **Strategy-internal**: Let the `CompactionStrategy.compact()` method decide internally — it receives the full message list and can return it unchanged if no compaction is needed. This is the simplest integration point (always call `compact()`, let the strategy no-op when appropriate) but has the overhead of calling into the strategy every iteration.

The recommended approach is **strategy-internal with a lightweight guard**: the `compact()` method is called after each tool result, but strategy implementations should include a fast short-circuit check (e.g., `if len(messages) < self.threshold: return False`) to minimize overhead when compaction is not needed. This keeps the tool loop simple (always call `compact()`) while letting each strategy define its own trigger logic.

The following example illustrates this for Variant A (in-place flat list). See Variant C under Option 1 for the simpler pre-grouped equivalent.

```python
class SlidingWindowStrategy(CompactionStrategy):
    """Example with built-in trigger logic and atomic group preservation (Variant A)."""

    def __init__(self, max_messages: int, *, compact_to: int | None = None):
        self.max_messages = max_messages
        self.compact_to = compact_to or max_messages // 2

    async def compact(self, messages: list[ChatMessage]) -> bool:
        # Fast short-circuit: no-op if under threshold
        if len(messages) <= self.max_messages:
            return False

        # Partition into anchors (system messages) and the rest
        anchors: list[ChatMessage] = []
        rest: list[ChatMessage] = []
        for m in messages:
            (anchors if m.role == "system" else rest).append(m)

        # Group into atomic units: [assistant w/ tool_calls + tool results]
        # count as one group; standalone messages are their own group
        groups: list[list[ChatMessage]] = []
        i = 0
        while i < len(rest):
            msg = rest[i]
            if msg.role == "assistant" and getattr(msg, "tool_calls", None):
                # Collect this assistant message + all following tool results
                group = [msg]
                i += 1
                while i < len(rest) and rest[i].role == "tool":
                    group.append(rest[i])
                    i += 1
                groups.append(group)
            else:
                groups.append([msg])
                i += 1

        # Keep the last N groups (by message count) that fit within compact_to
        kept: list[ChatMessage] = []
        count = 0
        for group in reversed(groups):
            if count + len(group) > self.compact_to:
                break
            kept = group + kept
            count += len(group)

        # Mutate in place
        messages.clear()
        messages.extend(anchors + kept)
        return True
```

#### Compaction on post-load, pre-write, and in-run

Given a situation where a compaction strategy is known, the following would need to happen:
1. At that moment in the run, the message list is passed to the strategy's `compact()` method, which returns whether compaction occurred (and depending on the variant, either mutates in place or returns a new list).
1. The caller continues with the (potentially reduced) list for the next steps (sending to the model, saving to storage, or continuing the tool loop with the reduced context)
1. We need to decide how to handle a failed compaction (e.g., the strategy raises an exception) — likely we should have a fallback to continue without compaction rather than failing the entire agent run.

#### Compaction on existing storage

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

2. **Add a `overwrite` parameter** to `save_messages()`:

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

This could then be combined with a convenience method on the provider for compaction:

```python

class HistoryProvider:

    compaction_strategy: CompactionStrategy | None = None  # Optional default strategy for this provider

    async def compact_storage(self, session_id: str | None, *, strategy: CompactionStrategy | None = None) -> None:
        """Compact stored history for this session using the given strategy."""
        history = await self.get_messages(session_id)
        used_strategy = strategy or self._get_strategy("existing") or self._get_strategy("post_load")
        if used_strategy is None:
            raise ValueError("No compaction strategy configured for existing storage.")
        await used_strategy.compact(history)
        await self.replace_messages(session_id, history)  # or save_messages with overwrite
        # or
        await self.save_messages(session_id, history, overwrite=True)
```

This design choice is orthogonal to the compaction strategy options below — any option requires one of these `HistoryProvider` extensions and optionally the convenience method.

## Decision Drivers

- **Applicable everywhere**: The same strategy object must work at post-load, pre-write, in-run (tool loop), and on existing storage
- **Composable with HistoryProvider**: Works naturally with the `HistoryProvider` subclass from ADR-0016
- **Composable with function calling**: Can be applied during the tool loop without requiring `ContextProvider` to run mid-loop
- **Cross-platform consistency**: The .NET SDK uses `IChatReducer` on `InMemoryChatHistoryProvider` with a `ChatReducerTriggerEvent` enum
- **Attribution-aware**: Can leverage `source_id` attribution on messages to make informed compaction decisions (e.g., preserve RAG context, remove ephemeral messages)
- **Chainable**: Multiple strategies must be composable in sequence (e.g., summarize older messages then truncate to fit token budget). In-place mutation on the same `list[ChatMessage]` enables piping one strategy into the next

## Considered Options

- Standalone `CompactionStrategy` object composed into `HistoryProvider` and `FunctionInvocationConfiguration`
- `CompactionStrategy` as a mixin for `HistoryProvider` subclasses
- Separate `CompactionProvider` set directly on the agent
- Mutable message access in `ChatMiddleware`


## Pros and Cons of the Options

### Option 1: Standalone `CompactionStrategy` Object

Define an abstract `CompactionStrategy` that can be **composed into any `HistoryProvider`** and also passed to the agent for in-run compaction.

There are three sub-variants for the `compact()` signature, which differ in mutability semantics and input structure:

#### Variant A: In-place mutation

The strategy mutates the provided list directly and returns `bool` indicating whether compaction occurred. Zero-allocation in the no-op case, and the tool loop doesn't need to reassign the list.

```python
class CompactionStrategy(ABC):
    """Abstract strategy for compacting a list of messages in place."""

    @abstractmethod
    async def compact(self, messages: list[ChatMessage]) -> bool:
        """Compact messages in place. Returns True if compaction occurred."""
        ...
```

#### Variant B: Return new list

The strategy returns a new list (leaving the original unchanged) plus a `bool` indicating whether compaction occurred. This is safer when the caller needs the original list preserved (e.g., for logging or fallback), and is a more functional style that avoids side-effect surprises.

```python
class CompactionStrategy(ABC):
    """Abstract strategy for compacting a list of messages."""

    @abstractmethod
    async def compact(self, messages: Sequence[ChatMessage]) -> tuple[list[ChatMessage], bool]:
        """Return (compacted_messages, did_compact)."""
        ...
```

Tool loop integration requires reassignment:

```python
# Inside the function invocation loop
messages.append(tool_result_message)
if config.get("compaction_strategy"):
    compacted, did_compact = await config["compaction_strategy"].compact(messages)
    if did_compact:
        messages.clear()
        messages.extend(compacted)
```

#### Variant C: Pre-grouped messages

Instead of receiving a flat list, the strategy receives pre-computed logical groups. This shifts the atomic-group-preservation burden from every strategy implementation to the framework, so strategy authors can focus on which groups to keep/remove/summarize without manually parsing message boundaries.

```python
@dataclass
class MessageGroup:
    """A logical group of messages that must be kept or removed together."""
    kind: Literal["system", "user", "assistant_text", "tool_call"]
    messages: list[ChatMessage]

    @property
    def length(self) -> int:
        """Number of messages in this group."""
        return len(self.messages)


class CompactionStrategy(ABC):
    """Abstract strategy operating on pre-grouped messages."""

    @abstractmethod
    async def compact(self, groups: list[MessageGroup]) -> bool:
        """Compact groups in place. Returns True if compaction occurred.

        Groups are pre-computed by the framework:
        - "system": system message(s)
        - "user": a single user message
        - "assistant_text": an assistant message without tool calls
        - "tool_call": an assistant message with tool_calls + all corresponding
          tool result messages (atomic unit)
        """
        ...
```

The framework handles grouping before calling `compact()` and flattening afterward:

```python
def _to_groups(messages: list[ChatMessage]) -> list[MessageGroup]:
    """Parse a flat message list into logical groups."""
    groups: list[MessageGroup] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.role == "system":
            groups.append(MessageGroup(kind="system", messages=[msg]))
            i += 1
        elif msg.role == "user":
            groups.append(MessageGroup(kind="user", messages=[msg]))
            i += 1
        elif msg.role == "assistant" and getattr(msg, "tool_calls", None):
            group_msgs = [msg]
            i += 1
            while i < len(messages) and messages[i].role == "tool":
                group_msgs.append(messages[i])
                i += 1
            groups.append(MessageGroup(kind="tool_call", messages=group_msgs))
        else:
            groups.append(MessageGroup(kind="assistant_text", messages=[msg]))
            i += 1
    return groups


def _flatten_groups(groups: list[MessageGroup]) -> list[ChatMessage]:
    """Flatten groups back into a flat message list."""
    return [msg for group in groups for msg in group.messages]


# Usage at a compaction point:
groups = _to_groups(messages)
did_compact = await strategy.compact(groups)
if did_compact:
    messages.clear()
    messages.extend(_flatten_groups(groups))
```

**Note on tool loop integration:** For in-run compaction with Variant C, the tool loop should maintain a `list[MessageGroup]` alongside the flat message list rather than re-parsing groups from scratch on every iteration. As the loop produces new messages, it appends them directly as groups (e.g., a `tool_call` group after collecting the assistant message and its tool results, or a standalone `assistant_text` group). The flat message list is only rebuilt from the groups when needed (after compaction, or before sending to the LLM). This avoids the O(n) re-grouping cost on every tool call iteration.

**Trade-offs between variants:**

| Aspect | Variant A (in-place) | Variant B (return new) | Variant C (pre-grouped) |
|--------|---------------------|----------------------|------------------------|
| **Allocation** | Zero in no-op case | Always allocates tuple | Grouping overhead always |
| **Safety** | Caller loses original | Original preserved | Caller loses original groups |
| **Strategy complexity** | Must handle atomic groups | Must handle atomic groups | Groups pre-computed by framework |
| **Chaining** | Natural (same list) | Pipe output to next input | Natural (same group list) |
| **Framework complexity** | Minimal | Reassignment logic | Grouping + flattening logic |

**Usage with `HistoryProvider`:**

The `compaction_strategy` parameter accepts either a single `CompactionStrategy` (applied at all applicable points) or a `CompactionStrategies` TypedDict for per-point configuration:

```python
class CompactionStrategies(TypedDict, total=False):
    """Per-point compaction strategy configuration."""
    post_load: CompactionStrategy
    pre_write: CompactionStrategy
    existing: CompactionStrategy


class HistoryProvider(ContextProvider):
    def __init__(
        self,
        source_id: str,
        *,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_responses: bool = True,
        # NEW: optional compaction — single strategy or per-point dict
        compaction_strategy: CompactionStrategy | CompactionStrategies | None = None,
    ): ...

    def _get_strategy(self, point: str) -> CompactionStrategy | None:
        """Resolve the strategy for a given compaction point."""
        if self.compaction_strategy is None:
            return None
        if isinstance(self.compaction_strategy, CompactionStrategy):
            return self.compaction_strategy
        return self.compaction_strategy.get(point)

    async def before_run(self, agent, session, context, state) -> None:
        history = await self.get_messages(context.session_id)
        if strategy := self._get_strategy("post_load"):
            await strategy.compact(history)
        context.extend_messages(self.source_id, history)

    async def after_run(self, agent, session, context, state) -> None:
        messages_to_store = self._collect_messages(context)
        if strategy := self._get_strategy("pre_write"):
            await strategy.compact(messages_to_store)
        if messages_to_store:
            await self.save_messages(context.session_id, messages_to_store)
```

**Simple usage (single strategy for all points):**

```python
strategy = SlidingWindowStrategy(max_messages=100)

agent = client.create_agent(
    context_providers=[
        InMemoryHistoryProvider("memory", compaction_strategy=strategy),
    ],
)
```

**Per-point usage (different strategies for different points):**

```python
agent = client.create_agent(
    context_providers=[
        InMemoryHistoryProvider(
            "memory",
            compaction_strategy={
                "post_load": SlidingWindowStrategy(max_messages=100),
                "pre_write": SummarizationStrategy(client, max_messages_before_summary=50),
            },
        ),
    ],
)
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
    await config["compaction_strategy"].compact(messages)
```

This means the same `CompactionStrategy` object can be reused across `HistoryProvider` (boundary compaction) and `FunctionInvocationConfiguration` (in-run compaction):

```python
strategy = SlidingWindowStrategy(max_messages=100)

agent = chat_client.create_agent(
    context_providers=[
        InMemoryHistoryProvider("memory", compaction_strategy=strategy),
    ],
    function_invocation_configuration={
        "max_iterations": 40,
        "compaction_strategy": strategy,  # Same strategy for tool loop
    },
)
```

Or leverage different strategies for different points (e.g., summarization on post-load, sliding window in-run):

```python
agent = client.create_agent(
    context_providers=[
        InMemoryHistoryProvider(
            "memory",
            compaction_strategy={
                "pre_write": SummarizationStrategy(client, max_messages_before_summary=50),
            },
        ),
    ],
    function_invocation_configuration={
        "max_iterations": 40,
        "compaction_strategy": SlidingWindowStrategy(max_messages=20),
    },
)
```

**Usage on existing storage (maintenance):**

```python
# Compact stored history outside of agent.run()
strategy = SlidingWindowStrategy(max_messages=100)
history = await my_history_provider.get_messages(session_id)
await strategy.compact(history)
await my_history_provider.save_messages(session_id, history)
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
- Good, because new strategies can be added without modifying `HistoryProvider`
- Good, because with Variant A (in-place), the tool loop integration is zero-allocation in the no-op case
- Good, because with Variant B (return new list), the caller retains the original list for logging or fallback
- Good, because with Variant C (pre-grouped), strategy authors don't need to implement atomic group preservation — the framework handles grouping/flattening, making strategies simpler and less error-prone
- Good, because it is easy to test strategies in isolation
- Good, because strategies can inspect `source_id` attribution on messages for informed decisions
- Good, because in-run compaction fits naturally into `FunctionInvocationConfiguration`, keeping all loop settings together
- Good, because **chaining is natural** — for Variants A/C, each strategy mutates the same list in sequence; for Variant B, output pipes into the next input
- Neutral, because Variant C adds framework complexity (grouping/flattening) but reduces strategy complexity
- Bad, because it adds a new concept (`CompactionStrategy`) alongside the existing `ContextProvider`/`HistoryProvider` hierarchy
- Bad, because Variant C introduces a `MessageGroup` model that must stay in sync with any future message role changes

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
- Bad, because **compaction strategy is coupled to the provider** — cannot share the same strategy across different providers, or in-run.
- Bad, because different strategies per compaction point (post-load vs pre-write) require additional configuration or separate methods
- Bad, because in-run compaction via `FunctionInvocationConfiguration` requires extracting the mixin from the provider list — unclear which one to use if multiple exist
- Bad, because `isinstance` checks are fragile and don't compose well
- Bad, because testing compaction requires instantiating a full provider rather than testing the strategy in isolation
- Bad, because existing storage compaction requires having the right provider type, not just any strategy
- Bad, because **chaining is difficult** — compaction logic is embedded in the provider's `compact()` override, so composing multiple strategies (e.g., summarize then truncate) requires subclass nesting or manual delegation within a single `compact()` method, rather than declarative composition

### Option 3: Separate `CompactionProvider` Set on the Agent

Define compaction as a special `ContextProvider` subclass that the agent calls at all compaction points (pre-load, pre-write, in-run (calls `compact`), existing storage). It is added to the agent's `context_providers` list like any other provider.

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
- Neutral, because **chaining is partially supported** — multiple `CompactionProvider` instances can be added to the provider list and will run in order during `before_run`/`after_run`, but in-run compaction via `FunctionInvocationConfiguration` only wires a single strategy (which one to pick is ambiguous), so chaining works at boundaries but not during the tool loop
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
- Neutral, because **chaining is implicit** — multiple compaction middleware can be stacked and will run in pipeline order, but there is no explicit composition model; middleware interact through side effects (mutating the shared message list) rather than declarative input/output, making chain behavior harder to reason about and debug
- Bad, because it requires **changing how the tool loop manages messages** — the current copy-based architecture must be rethought
- Bad, because multiple middleware could conflict when replacing messages (no coordination)
- Bad, because it does **not cover existing storage compaction**
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
| Interface | `IChatReducer` with `ReduceAsync(messages) -> messages` | `CompactionStrategy.compact()` with three signature variants (Options 1-3) / `ChatMiddleware` mutation (Option 4) |
| Attachment | Property on `InMemoryChatHistoryProvider` | Composed into `HistoryProvider` (Option 1) / mixin (Option 2) / separate provider (Option 3) / middleware (Option 4) |
| Trigger | `ChatReducerTriggerEvent` enum: `AfterMessageAdded`, `BeforeMessagesRetrieval` | Post-load + pre-write + in-run + storage maintenance (Options 1-3) / in-run + post-load only (Option 4) |
| Scope | Only within `InMemoryChatHistoryProvider` | Applicable to any `HistoryProvider` and the tool loop (Option 1) |

Option 1's `CompactionStrategy` is the closest equivalent to .NET's `IChatReducer`, with a broader scope.

### Coverage Matrix

How each option addresses the four compaction points and the current architectural limitations:

| Compaction Point | Option 1 (Strategy) | Option 2 (Mixin) | Option 3 (Provider) | Option 4 (Middleware) |
|-----------------|---------------------|-------------------|---------------------|-----------------------|
| **Post-load** | ✅ `HistoryProvider` param | ✅ `compact()` override | ✅ `before_run` | ✅ Middleware before LLM |
| **Pre-write** | ✅ `HistoryProvider` param | ⚠️ Needs extra method | ⚠️ `after_run` override | ❌ Not supported |
| **In-run (tool loop)** | ✅ `FunctionInvocationConfiguration` | ⚠️ Awkward extraction | ⚠️ `isinstance` wiring | ⚠️ Requires refactoring copy semantics |
| **Existing storage** | ✅ Standalone `compact()` | ✅ Provider's `compact()` | ✅ Standalone `compact()` | ❌ Not supported |
| **Solves copy problem** | ✅ Runs inside loop | ⚠️ Indirectly | ⚠️ Indirectly | ⚠️ Requires deep refactor |
| **Chaining** | ✅ Natural composition via wrapper | ❌ Coupled to provider | ⚠️ Boundary only, not in-run | ⚠️ Implicit via stacking |
| **New concepts** | 1 (`CompactionStrategy`) | 1 (mixin) | 0.5 (reuses `ContextProvider`, but adds new method) | 0 (reuses `ChatMiddleware`) |

## More Information

### Message Attribution and Compaction

The `source_id` attribution system from ADR-0016 enables intelligent compaction:

```python
class AttributionAwareStrategy(CompactionStrategy):
    """Example: remove ephemeral context but preserve RAG and user messages."""

    async def compact(self, messages: list[ChatMessage]) -> bool:
        ephemeral = [m for m in messages if m.additional_properties.get("source_id") == "ephemeral"]
        if not ephemeral:
            return False
        for msg in ephemeral:
            messages.remove(msg)
        return True
```

### Related Decisions

- [ADR-0016: Unifying Context Management with ContextPlugin](0016-python-context-middleware.md) — Parent ADR that established `ContextProvider`, `HistoryProvider`, and `AgentSession` architecture.
- [Context Compaction Limitations Analysis](https://gist.github.com/victordibia/ec3f3baf97345f7e47da025cf55b999f) — Detailed analysis of why current architecture cannot support in-run compaction, with attempted solutions and their failure modes. Option 4 in this ADR corresponds to "Option A: Middleware Access to Mutable Message Source" from that analysis; Options 1-3 correspond to "Option B: Tool Loop Hook" (via `FunctionInvocationConfiguration`).
