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

### Message-list correctness constraint: Atomic group preservation

A critical correctness constraint for any compaction strategy: **tool calls and their results must be kept together**. LLM APIs (OpenAI, Azure, etc.) require that an assistant message containing `tool_calls` is always followed by corresponding `tool` result messages. A compaction strategy that removes one without the other will cause API errors. This is extended for reasoning models, at least in the OpenAI Responses API with a Reasoning content, without it you also get failed calls.

Strategies must treat `[assistant message with tool_calls] + [tool result messages]` as atomic groups — either keep the entire group or remove it entirely. Option 1 addresses this structurally in both Variant C1 (precomputed `MessageGroups`) and Variant C2 (precomputed `_group_*` annotations on messages), so strategy authors do not need to rediscover raw boundaries on every pass.

### Where Compaction Is Needed

Compaction must be applicable in **three primary points** in the agent lifecycle:

| Point | When | Purpose |
|-------|------|---------|
| **In-run** | During the (potentially) multiple calls to a ChatClient's `get_response` within a single `agent.run()` | Keep context within limits as tool calls accumulate and project only included messages per model call |
| **Pre-write\*** | Before `HistoryProvider.save_messages()` in `after_run` | Compact before persisting to storage, limiting storage size, _only applies to messages from a run_ |
| **On existing storage\*** | Outside of `agent.run()`, as a maintenance operation | Compact stored history (e.g., cron job, manual trigger) |

**\***: Should pre-write and existing-storage compaction share one unified configuration/setup to reduce duplicate strategy wiring, and then either: each write overrides the full storage, or only new messages are compacted while a separate interface can be called to compact the existing storage?

### Scope: Not Applicable to Service-Managed Storage

**All compaction discussed in this ADR is irrelevant when using only service-managed storage** (`service_session_id` is set). In that scenario:
- The service manages message history internally — the client never holds the full conversation
- Only new messages are sent to/from the service each turn
- The service is responsible for its own context window management and compaction
- The client has no message list to compact

This ADR applies to two scenarios where the **client** constructs and manages the message list sent to the model:

1. **With local storage** (e.g., `InMemoryHistoryProvider`, Redis, Cosmos) — compaction is needed during a run, currently no compaction is done in our abstractions.
2. **Without any storage** (`store=False`, no `HistoryProvider`) — in-run compaction is still critical for long-running, tool-heavy agent invocations where the message list grows unbounded within a single `agent.run()` call

## Decision Drivers

- **Applicable across primary points**: The strategy model must work at pre-write, in-run, and on existing storage, this means it must be:
    - **Composable with HistoryProvider**: Works naturally with the `HistoryProvider` subclass from ADR-0016
    - **Composable with function calling/chat clients**: Can be applied during the inner loop of the chat clients
- **Message-list correctness**: Compaction must preserve required assistant/tool/result ordering and reasoning/tool-call pairings so the model input stays valid
- **Chainable**/**Composable**: Multiple strategies must be composable (e.g., summarize older messages then truncate to fit token budget).

## Considered Options

- Standalone `CompactionStrategy` object composed into `HistoryProvider` and `ChatClient`
- `CompactionStrategy` as a mixin for `HistoryProvider` subclasses
- Separate `CompactionProvider` set directly on the agent
- Mutable message access in `ChatMiddleware`


## Pros and Cons of the Options

### Option 1: Standalone `CompactionStrategy` Object

Define an abstract `CompactionStrategy` that can be **composed into any `HistoryProvider`** and also passed to the agent for in-run compaction.

There are three sub-variants for the method signature, which differ in mutability semantics and input structure, all of them use `__call__` to be easily used as a callable, and allow simple strategies to be expressed as simple functions, and if you need additional state or helper methods you can implement a class with `__call__`:

#### Variant A: In-place mutation

The strategy mutates the provided list directly and returns `bool` indicating whether compaction occurred. Zero-allocation in the no-op case, and the tool loop doesn't need to reassign the list.

```python
@runtime_checkable
class CompactionStrategy(Protocol):
    """Abstract strategy for compacting a list of messages in place."""

    async def __call__(self, messages: list[Message]) -> bool:
        """Compact messages in place. Returns True if compaction occurred."""
        ...
```

#### Variant B: Return new list

The strategy returns a new list (leaving the original unchanged) plus a `bool` indicating whether compaction occurred. This is safer when the caller needs the original list preserved (e.g., for logging or fallback), and is a more functional style that avoids side-effect surprises.

```python
@runtime_checkable
class CompactionStrategy(Protocol):
    """Abstract strategy for compacting a list of messages."""

    async def __call__(self, messages: Sequence[Message]) -> tuple[list[Message], bool]:
        """Return (compacted_messages, did_compact)."""
        ...
```

Tool loop integration requires reassignment:

```python
# Inside the function invocation loop
messages.append(tool_result_message)
if compacter := config.get("compaction_strategy"):
    compacted, did_compact = await compacter(messages)
    if did_compact:
        messages.clear()
        messages.extend(compacted)
```

#### Variant C: Group-aware compaction entry points

Variant C has two sub-variants that provide the same logical grouping behavior:
- **C1 (`MessageGroups` state object):** group metadata lives in a sidecar container.
- **C2 (`_`-prefixed message attributes):** group metadata lives directly on messages in `additional_properties`.

Both approaches let strategies operate on logical units (`system`, `user`, `assistant_text`, `tool_call`) instead of re-deriving boundaries every time.

##### Variant C1: `MessageGroups` sidecar state

```python
@dataclass
class MessageGroup:
    """A logical group of messages that must be kept or removed together."""
    kind: Literal["system", "user", "assistant_text", "tool_call"]
    messages: list[Message]

    @property
    def length(self) -> int:
        """Number of messages in this group."""
        return len(self.messages)


@dataclass
class MessageGroups:
    groups: list[MessageGroup]

    @classmethod
    def from_messages(cls, messages: list[Message]) -> "MessageGroups":
        """Build grouped state from a flat message list."""
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
        return cls(groups)

    def summary(self) -> dict[str, int]:
        return {
            "group_count": len(self.groups),
            "message_count": sum(len(g.messages) for g in self.groups),
            "tool_call_count": sum(1 for g in self.groups if g.kind == "tool_call"),
        }

    def to_messages(self) -> list[Message]:
        """Flatten grouped state back into a flat message list."""
        return [msg for group in self.groups for msg in group.messages]


class CompactionStrategy(Protocol):
    """Callable strategy for group-aware compaction."""

    async def __call__(self, groups: MessageGroups) -> bool:
        """Compact by mutating grouped state. Returns True if changed.

        Group kinds:
        - "system": system message(s)
        - "user": a single user message
        - "assistant_text": an assistant message without tool calls
        - "tool_call": an assistant message with tool_calls + all corresponding
          tool result messages (atomic unit)
        """
        ...
```

Class-based strategies implement `__call__` directly:

```python
class ExcludeOldestGroupsStrategy:
    async def __call__(self, groups: MessageGroups) -> bool:
        # Mutate grouped state in place.
        ...
```

The framework builds and flattens grouped state through `MessageGroups` methods:

```python
# Usage at a compaction point:
groups = MessageGroups.from_messages(messages)
logger.debug("Pre-compaction summary: %s", groups.summary())
# optional also emit OTEL events next to these loggers, but not sure if needed
await strategy(groups)
logger.debug("Post-compaction summary: %s", groups.summary())
response = await get_response(messages=groups.to_messages())
# add messages from response into new group and to the groups.
```

**Note on tool loop integration (C1):** For in-run compaction with Variant C1, the function-invocation layer will maintain a `MessageGroups` object (instead of repeatedly rebuilding groups from a flat list). As the loop produces new messages, it appends them directly as groups (e.g., a `tool_call` group after collecting the assistant message and its tool results, or a standalone `assistant_text` group). The flat message list is only rebuilt from groups when needed (after compaction, or before sending to the LLM). This avoids O(n) re-grouping on every tool-call iteration.

##### Variant C2: `_`-prefixed metadata directly on `Message`

Variant C2 achieves the same grouping behavior as C1 but stores grouping metadata on messages instead of in a sidecar `MessageGroups` object.

```python
def _annotate_groups(messages: list[Message]) -> None:
    """Annotate messages with group metadata in additional_properties.

    Metadata keys:
    - "_group_id": stable group id for all messages in the same logical unit
    - "_group_kind": "system" | "user" | "assistant_text" | "tool_call"
    - "_group_index": order of groups in the current list
    """
    group_index = 0
    i = 0
    while i < len(messages):
        msg = messages[i]
        group_id = f"g-{group_index}"
        if msg.role == "assistant" and getattr(msg, "tool_calls", None):
            msg.additional_properties["_group_id"] = group_id
            msg.additional_properties["_group_kind"] = "tool_call"
            msg.additional_properties["_group_index"] = group_index
            i += 1
            while i < len(messages) and messages[i].role == "tool":
                messages[i].additional_properties["_group_id"] = group_id
                messages[i].additional_properties["_group_kind"] = "tool_call"
                messages[i].additional_properties["_group_index"] = group_index
                i += 1
        else:
            kind = (
                "system" if msg.role == "system"
                else "user" if msg.role == "user"
                else "assistant_text"
            )
            msg.additional_properties["_group_id"] = group_id
            msg.additional_properties["_group_kind"] = kind
            msg.additional_properties["_group_index"] = group_index
            i += 1
        group_index += 1


class CompactionStrategy(Protocol):
    async def __call__(self, messages: list[Message]) -> bool:
        """Compact using message annotations; mutate in place."""
        ...
```

**Note on tool loop integration (C2):** The loop should annotate new messages incrementally as they are appended (rather than re-running `_annotate_groups` over the full list every iteration). For example, when a tool call completes, tag the assistant tool-call message and all tool results with the same `_group_id`.

#### Variant D: Exclude-based projection (builds on Variant C1/C2)

Variant D also has two sub-variants:
- **D1:** exclusion state on `MessageGroup`.
- **D2:** exclusion state on message `_`-attributes.

##### Variant D1: exclusion state on `MessageGroup`

```python
@dataclass
class MessageGroup:
    kind: Literal["system", "user", "assistant_text", "tool_call"]
    messages: list[Message]
    excluded: bool = False
    exclude_reason: str | None = None


@dataclass
class MessageGroups:
    groups: list[MessageGroup]

    def summary(self) -> dict[str, int]:
        return {
            "group_count": len(self.groups),
            "message_count": sum(len(g.messages) for g in self.groups),
            "tool_call_count": sum(1 for g in self.groups if g.kind == "tool_call"),
            "included_group_count": sum(1 for g in self.groups if not g.excluded),
            "included_message_count": sum(len(g.messages) for g in self.groups if not g.excluded),
            "included_tool_call_count": sum(
                1 for g in self.groups if g.kind == "tool_call" and not g.excluded
            ),
        }

    def get_messages(self, *, excluded: bool = False) -> list[Message]:
        if excluded:
            return [msg for g in self.groups for msg in g.messages]
        return [msg for g in self.groups if not g.excluded for msg in g.messages]

    def included_messages(self) -> list[Message]:
        return self.get_messages(excluded=False)
```

During compaction, strategies/orchestrators mutate `group.excluded`/`group.exclude_reason` (including re-including groups with `excluded=False`) instead of discarding data.

##### Variant D2: exclusion state on message `_`-attributes

```python
def set_group_excluded(messages: list[Message], *, group_id: str, reason: str | None = None) -> None:
    for msg in messages:
        if msg.additional_properties.get("_group_id") == group_id:
            msg.additional_properties["_excluded"] = True
            msg.additional_properties["_exclude_reason"] = reason


def clear_group_excluded(messages: list[Message], *, group_id: str) -> None:
    for msg in messages:
        if msg.additional_properties.get("_group_id") == group_id:
            msg.additional_properties["_excluded"] = False
            msg.additional_properties["_exclude_reason"] = None


def included_messages(messages: list[Message]) -> list[Message]:
    return [m for m in messages if not m.additional_properties.get("_excluded", False)]
```

In D2, strategies project included context by filtering on `_excluded` instead of filtering `MessageGroup` objects.

#### Variant E: Tokenization and accounting (builds on Variant C1/C2)

Variant E has two sub-variants:
- **E1:** token rollups cached on `MessageGroup`/`MessageGroups`.
- **E2:** token rollups cached directly on messages via `_`-attributes.

##### Variant E1: token rollups on grouped state

Variant E1 adds tokenization metadata and cached token rollups to grouped state. This is independent of exclusion: token-aware strategies can use token metrics even if no groups are excluded. When combined with Variant D, token budgets can be enforced against included messages.

To make token-budget compaction deterministic:
1. Before **every** `get_response` call in the tool loop, tokenize every message currently in `all_messages` (regardless of source).
2. Persist per-content token counts in `content.additional_properties["_token_count"]`.
3. Build/update grouped state from tokenized messages and use cached rollups for threshold checks and summaries.

```python
class TokenizerProtocol(Protocol):
    def count_tokens(self, content: AIContent, *, model_id: str | None = None) -> int: ...


@dataclass
class MessageGroup:
    kind: Literal["system", "user", "assistant_text", "tool_call"]
    messages: list[Message]
    _token_count_cache: int | None = None

    def token_count(self) -> int:
        if self._token_count_cache is None:
            self._token_count_cache = sum(
                content.additional_properties.get("_token_count", 0)
                for message in self.messages
                for content in message.contents
            )
        return self._token_count_cache


@dataclass
class MessageGroups:
    groups: list[MessageGroup]
    _total_tokens_cache: int | None = None

    def total_tokens(self) -> int:
        if self._total_tokens_cache is None:
            self._total_tokens_cache = sum(group.token_count() for group in self.groups)
        return self._total_tokens_cache

    def summary(self) -> dict[str, int]:
        return {
            "group_count": len(self.groups),
            "message_count": sum(len(g.messages) for g in self.groups),
            "tool_call_count": sum(1 for g in self.groups if g.kind == "tool_call"),
            "total_tokens": self.total_tokens(),
            "tool_call_tokens": sum(g.token_count() for g in self.groups if g.kind == "tool_call"),
        }
```
And the following helper method should also be added:

```python
def _to_tokenized_groups(
    messages: list[Message], *, tokenizer: TokenizerProtocol
) -> MessageGroups:
    tokenize_messages(messages, tokenizer=tokenizer)
    return MessageGroups.from_messages(messages)
```

##### Variant E2: token rollups on message `_`-attributes

```python
def annotate_token_counts(messages: list[Message], *, tokenizer: TokenizerProtocol) -> None:
    for message in messages:
        message_token_count = 0
        for content in message.contents:
            count = tokenizer.count_tokens(content)
            content.additional_properties["_token_count"] = count
            message_token_count += count
        message.additional_properties["_message_token_count"] = message_token_count


def sum_tokens_by_group(messages: list[Message]) -> dict[str, int]:
    """Compute group totals on demand from `_message_token_count`."""
    tokens_by_group: dict[str, int] = {}
    for message in messages:
        group_id = message.additional_properties["_group_id"]
        tokens_by_group[group_id] = tokens_by_group.get(group_id, 0) + message.additional_properties.get(
            "_message_token_count", 0
        )
    return tokens_by_group
```

In E2, strategies evaluate `_message_token_count`/`_token_count` directly from messages and compute per-group totals on demand via `_group_id` (instead of caching `_group_token_count` on every message). This avoids duplicated state and ambiguity when one copy is updated but others are stale. If needed for performance, the function-invocation loop can keep an ephemeral `dict[group_id, token_count]` alongside the annotated message list.

#### Variant F: Combined projection + tokenization (C + D + E)

Variant F has two sub-variants:
- **F1:** combined model on `MessageGroups`.
- **F2:** combined model on `_`-annotated messages.

##### Variant F1: combined model on `MessageGroups`

Variant F1 combines Variant C1's grouped interface, Variant D1's exclusion semantics, and Variant E1's token accounting in one integrated model. This gives one state container for projection (`excluded`) and budget control (`token_count`), while preserving full history for final-return and diagnostics.

For Variant F1, `MessageGroups.from_messages(...)` accepts an optional tokenizer and handles both tokenization and grouping before strategy execution:

```python
class TokenizerProtocol(Protocol):
    def count_tokens(self, content: AIContent, *, model_id: str | None = None) -> int: ...


@dataclass
class MessageGroup:
    kind: Literal["system", "user", "assistant_text", "tool_call"]
    messages: list[Message]
    excluded: bool = False
    exclude_reason: str | None = None
    _token_count_cache: int | None = None

    def token_count(self) -> int:
        if self._token_count_cache is None:
            self._token_count_cache = sum(
                content.additional_properties.get("_token_count", 0)
                for message in self.messages
                for content in message.contents
            )
        return self._token_count_cache


@dataclass
class MessageGroups:
    groups: list[MessageGroup]
    _total_tokens_cache: int | None = None

    @classmethod
    def from_messages(
        cls,
        messages: list[Message],
        *,
        tokenizer: TokenizerProtocol | None = None,
    ) -> "MessageGroups":
        if tokenizer is not None:
            tokenize_messages(messages, tokenizer=tokenizer)
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
        return cls(groups)

    def get_messages(self, *, excluded: bool = False) -> list[Message]:
        if excluded:
            return [msg for g in self.groups for msg in g.messages]
        return [msg for g in self.groups if not g.excluded for msg in g.messages]

    def included_messages(self) -> list[Message]:
        return self.get_messages(excluded=False)

    def total_tokens(self) -> int:
        if self._total_tokens_cache is None:
            self._total_tokens_cache = sum(group.token_count() for group in self.groups)
        return self._total_tokens_cache

    def included_token_count(self) -> int:
        return sum(g.token_count() for g in self.groups if not g.excluded)

    def summary(self) -> dict[str, int]:
        return {
            "group_count": len(self.groups),
            "message_count": sum(len(g.messages) for g in self.groups),
            "tool_call_count": sum(1 for g in self.groups if g.kind == "tool_call"),
            "included_group_count": sum(1 for g in self.groups if not g.excluded),
            "included_message_count": sum(len(g.messages) for g in self.groups if not g.excluded),
            "included_tool_call_count": sum(
                1 for g in self.groups if g.kind == "tool_call" and not g.excluded
            ),
            "total_tokens": self.total_tokens(),
            "tool_call_tokens": sum(g.token_count() for g in self.groups if g.kind == "tool_call"),
            "included_tokens": self.included_token_count(),
        }


class CompactionStrategy(Protocol):
    async def __call__(self, groups: MessageGroups) -> None:
        """Mutate the provided groups in place."""
        ...
```

##### Variant F2: combined model on `_`-annotated messages

```python
class CompactionStrategy(Protocol):
    async def __call__(self, messages: list[Message]) -> bool:
        """Mutate message annotations in place."""
        ...


async def compact_with_annotations(
    messages: list[Message], *, strategy: CompactionStrategy, tokenizer: TokenizerProtocol
) -> list[Message]:
    # C2: annotate group boundaries
    _annotate_groups(messages)
    # E2: annotate token metrics
    annotate_token_counts(messages, tokenizer=tokenizer)
    _ = sum_tokens_by_group(messages)  # optional ephemeral aggregate in loop state

    # D2/F2: strategy toggles _excluded/_exclude_reason and can rewrite messages
    _ = await strategy(messages)

    # Project only included messages for model call
    return [m for m in messages if not m.additional_properties.get("_excluded", False)]
```

F2 avoids a sidecar object but requires strict ownership rules for `_` attributes (who sets, updates, clears, and validates them).

**Trade-offs between variants:**

| Aspect | Variant A (in-place) | Variant B (return new) | Variant C1 (`MessageGroups`) | Variant C2 (`_` attrs) | Variant D1 (`MessageGroups` exclude) | Variant D2 (`_excluded` attrs) | Variant E1 (group token caches) | Variant E2 (message token attrs + on-demand group sums) | Variant F1 (`MessageGroups` combined) | Variant F2 (`_` attrs combined) |
|--------|---------------------|----------------------|-------------------------------|-----------------------|--------------------------------------|-------------------------------|----------------------------------|-------------------------------------|-----------------------------------|----------------------------------|
| **Allocation** | Zero in no-op case | Always allocates tuple | Grouping sidecar allocation | No sidecar; metadata writes | D1 + exclusion state | D2 + metadata writes | E1 + token cache sidecar | E2 + message metadata writes | Highest sidecar state | No sidecar; highest metadata writes |
| **Safety** | Caller loses original | Original preserved | State isolated in sidecar | Metadata mutates source messages | Full grouped history preserved | Full message history preserved | Deterministic token rollups in sidecar | Deterministic token rollups on messages | Strong isolation of all compaction state | Shared-message mutation can leak across layers |
| **Strategy complexity** | Must handle atomic groups | Must handle atomic groups | Groups pre-computed by framework | Reads `_group_*` fields | Exclude/re-include by group | Exclude/re-include by `_group_id` | Token budget via group APIs | Token budget via `_token*` fields | Unified exclude + token policy via group APIs | Unified policy via many message attrs |
| **Chaining** | Natural (same list) | Pipe output to next input | Natural (same group state) | Natural (same annotated message list) | Natural | Natural | Natural | Natural | Natural | Natural |
| **Framework complexity** | Minimal | Reassignment logic | Grouping + flattening layer | Annotation lifecycle/validation | C1 + exclusion semantics | C2 + projection/filter semantics | C1 + tokenizer + cache invalidation | C2 + tokenizer + attr invalidation | Highest sidecar orchestration | Highest attr lifecycle orchestration |

**Usage with `HistoryProvider`:**

The `compaction_strategy` parameter accepts either a single `CompactionStrategy` or it can take a composed/chained strategy.

```python

class HistoryProvider(ContextProvider):
    def __init__(
        self,
        source_id: str,
        *,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_responses: bool = True,
        # NEW: optional compaction strategy, can be a single strategy or a chained/composed strategy
        compaction_strategy: CompactionStrategy | None = None,
        # NEW: optional tokenizer for token-aware compaction strategies
        tokenizer: TokenizerProtocol | None = None,
    ): ...

    async def after_run(self, agent, session, context, state) -> None:
        messages_to_store = self._collect_messages(context)
        groups = MessageGroups.from_messages(messages_to_store, tokenizer=self.tokenizer)
        if self.compaction_strategy:
            await self.compaction_strategy(groups)
        messages_to_store = groups.to_messages()
        if messages_to_store:
            await self.save_messages(context.session_id, messages_to_store)
```

**Simple usage:**

```python
strategy = SlidingWindowStrategy(max_messages=100)

agent = client.create_agent(
    context_providers=[
        InMemoryHistoryProvider("memory", compaction_strategy=strategy),
    ],
)
```

There are two ways we can do this:
1. Before writing to storage in `after_run`, compaction is called on the new messages,
    combined with: a new `compact` method, that reads the full history, calls the compaction strategy with the full history, then writes the compacted result back to storage (also requires a `overwrite` flag on the `save_messages` method). This makes removing old messages from storage a explicit action that the user initiaties instead of being implicitly triggered by `after_run` writes, but it also means compaction strategies only see new messages instead of the full history (unless they read it themselves), the `compact` method could then also have a override for the strategy to use (and/or the tokenizer in case of Variant E1/E2/F1/F2).

    ```python
    class HistoryProvider(ContextProvider):
        ...
        async def compact(self, session_id: str, *, strategy: CompactionStrategy | None = None, tokenizer: TokenizerProtocol | None = None) -> None:
            history = await self.get_messages(session_id)
            if tokenizer:
                tokenize_messages(history, tokenizer=tokenizer)
            applicable_strategy = strategy or self.compaction_strategy
            await applicable_strategy(history)  # compaction mutates history in place or returns new list depending on variant
            await self.save_messages(session_id, history, overwrite=True)  # write compacted history back to storage
    ```

2. Before writing the history is loaded (could already be in-memory from `before_run`), compaction is called on the full history (old + new), then the compacted result is written back to storage. This allows compaction strategies to consider the full history when deciding what to keep, but it also means the provider needs to support writing the full history back (not just appending new messages).

Given the explicit nature, and the ability to do the heavy lifting of reading, compacting and writing outside of the agent loop, we decide to go with the first setup, if we decide to use Option 1 overall.

**Usage for in-run compaction (tool loop):**

In-run compaction is executed within the Function Calling Layer, this loop is controlled by the existing TypedDict that controls the function calling loop (max iterations, error handling, etc.). Adding compaction and return-shape fields keeps loop-related behavior in one place.

For token-aware variants (E1/E2/F1/F2), a tokenizer must also be configured because token counts are part of compaction decisions, this could be optional to allow simple compaction strategies that don't use token metrics. For the grouped-state path (F1), use `MessageGroups.from_messages(..., tokenizer=...)` so tokenization and grouping happen together before strategy invocation.

```python
class FunctionInvocationConfiguration(TypedDict, total=False):
    enabled: bool
    max_iterations: int
    max_consecutive_errors_per_request: int
    terminate_on_unknown_calls: bool
    additional_tools: Sequence[ToolProtocol]
    include_detailed_errors: bool
    compaction_strategy: CompactionStrategy | None  # NEW
    tokenizer: TokenizerProtocol | None  # NEW; required for token-aware variants (E1/E2/F1/F2)
    include_excluded_messages_in_final_response: bool  # NEW; default True
```

However these should *also* be first-class parameters on `Agent`, then propagated and stored into `FunctionInvocationConfiguration` at agent creation time:

```python
agent = Agent(
    client=chat_client,
    context_providers=[
        InMemoryHistoryProvider("memory", compaction_strategy=boundary_strategy),
    ],
    compaction_strategy=compaction_strategy,
    tokenizer=model_tokenizer,  # required for token-aware variants (E1/E2/F1/F2)
)
```

During the function calling loop, the strategy should be applied immediately before **every** `get_response` call (each model roundtrip):

```python
# Inside the function invocation loop (e.g., in _try_execute_function_calls)
logger = logging.getLogger(__name__)
groups = MessageGroups.from_messages(
    all_messages,
    tokenizer=config["tokenizer"],  # required for token-aware variants (E1/E2/F1/F2)
)
group_metrics = groups.summary()

if config.get("compaction_strategy"):
    before_compaction = groups.summary()
    await config["compaction_strategy"](groups)
    after_compaction = groups.summary()
    logger.info(
        "In-run compaction applied",
        strategy=type(config["compaction_strategy"]).__name__,
        summary_before=before_compaction,
        summary_after=after_compaction,
    )
    # Strategies can set groups.groups[i].excluded True/False with reasons

response = await super_get_response(messages=groups.included_messages(), ...)
# tokenize and store response messages, append to all_messages/groups as new groups, then next loop iteration will re-apply compaction with updated state
```

After the loop completes, final response shape is controlled by config:

```python
return_messages = groups.get_messages(excluded=config.get("include_excluded_messages_in_final_response", True))
```

Even with Variant A as the baseline, grouped exclusion metadata can be maintained in the function-invocation layer while only included messages are sent to `get_response`.

**Built-in strategies:**

```python
class TruncationStrategy(CompactionStrategy):
    """Keep the last N messages, optionally preserving the system message."""
    def __init__(self, *, max_messages: int, max_tokens: int, preserve_system: bool = True): ...

class SlidingWindowStrategy(CompactionStrategy):
    """Keep system message + last N messages."""
    def __init__(self, *, max_messages: int, max_tokens: int): ...

class SummarizationStrategy(CompactionStrategy):
    """Summarize older messages using an LLM."""
    def __init__(self, *, client: ..., max_messages_before_summary: int, max_tokens_before_summary: int): ...

# etc
```

**Opinionated token budget based composed strategy pattern (Variant F1/F2):**

This ADR proposes shipping a built-in composed strategy that enforces a token budget by running a list of regular strategies from top to bottom until the conversation fits the budget. This is intentionally opinionated and serves as a practical default/inspiration; advanced users can still implement custom orchestration logic. In F1, this strategy should drive `MessageGroup.excluded`; in F2, it should drive message `_excluded` annotations so model calls project only included context while preserving the full list.

```python
class TokenBudgetComposedStrategy(CompactionStrategy):
    def __init__(
        self,
        *,
        token_budget: int,
        strategies: Sequence[CompactionStrategy],
        early_stop: bool = False,  # optional flag to stop after first strategy that meets the budget, or run all strategies regardless
    ):
        self.token_budget = token_budget
        self.strategies = strategies
        self.early_stop = early_stop

    async def __call__(self, groups: MessageGroups) -> None:
        if groups.included_token_count() <= self.token_budget:
            return

        for strategy in self.strategies:
            await strategy(groups)

            if self.early_stop and groups.included_token_count() <= self.token_budget:
                break
```

This pattern keeps composition explicit and deterministic: ordered strategies, shared token metric, exclusion-flag semantics, optional re-inclusion by later strategies, and early stop as soon as budget is satisfied.

- Good, because the same strategy model works at the three primary compaction points (pre-write, in-run, existing storage)
- Good, because strategies are fully reusable — one instance can be shared across providers and agents
- Good, because new strategies can be added without modifying `HistoryProvider`
- Good, because with Variant A (in-place), the tool loop integration is zero-allocation in the no-op case
- Good, because with Variant B (return new list), the caller retains the original list for logging or fallback
- Good, because with Variants C1-F1 (grouped-state), strategy authors don't need to implement atomic group preservation — the framework handles grouping/flattening, making strategies simpler and less error-prone
- Good, because with Variants C2-F2 (message annotations), we can avoid a sidecar `MessageGroups` container while still preserving logical groups through `_group_*` attributes
- Good, because it is easy to test strategies in isolation
- Good, because strategies can inspect `source_id` attribution on messages for informed decisions
- Good, because in-run settings can be first-class `Agent` parameters while still being stored in `FunctionInvocationConfiguration` for loop execution
- Good, because **chaining is natural** — for Variants A/C1-F2, each strategy mutates the same shared state in sequence; for Variant B, output pipes into the next input
- Neutral, because Variants C1-F2 add framework complexity (grouping/flattening or annotation lifecycle, plus tokenization/exclusion accounting) but reduce strategy complexity
- Bad, because it adds a new concept (`CompactionStrategy`) alongside the existing `ContextProvider`/`HistoryProvider` hierarchy
- Bad, because Variants C1-F1 introduce a `MessageGroup` model that must stay in sync with any future message role changes
- Bad, because Variants C2-F2 depend on careful `_`-attribute lifecycle management to avoid stale or inconsistent annotations

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
- Bad, because different strategies per compaction point (pre-write vs existing) require additional configuration or separate methods
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
        """Compact messages loaded by previous providers before model invocation."""
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

Chosen option: **Option 1: Standalone `CompactionStrategy` Object** with **F2** (`_`-annotated messages) as the primary implementation model. We still document F1 as a valid alternative, but F2 is preferred because it introduces one less concept (no sidecar `MessageGroups` container) and enables native state sharing across compaction points (e.g., between the function-calling loop and `HistoryProvider.after_run`), improving efficiency by reducing translation/rebuild steps.

## Comparison to .NET Implementation

The .NET SDK uses `IChatReducer` composed into `InMemoryChatHistoryProvider`:

| Aspect | .NET | Proposed Options |
|--------|------|-----------------|
| Interface | `IChatReducer` with `ReduceAsync(messages) -> messages` | `CompactionStrategy.compact()` with three signature variants (Options 1-3) / `ChatMiddleware` mutation (Option 4) |
| Attachment | Property on `InMemoryChatHistoryProvider` | Composed into `HistoryProvider` (Option 1) / mixin (Option 2) / separate provider (Option 3) / middleware (Option 4) |
| Trigger | `ChatReducerTriggerEvent` enum: `AfterMessageAdded`, `BeforeMessagesRetrieval` | Pre-write + in-run + storage maintenance (Options 1-3 primary scope); post-load-style behavior can be covered by in-run pre-send projection |
| Scope | Only within `InMemoryChatHistoryProvider` | Applicable to any `HistoryProvider` and the tool loop (Option 1) |

Option 1's `CompactionStrategy` is the closest equivalent to .NET's `IChatReducer`, with a broader scope.

### Achieving the same scenarios in MEAI/.NET

| Python scenario | .NET/MEAI mechanism | How it maps |
|-----------------|---------------------|-------------|
| **Pre-write compaction** | `InMemoryChatHistoryProvider` + `ChatReducerTriggerEvent.AfterMessageAdded` | Reducer runs in `StoreChatHistoryAsync` after new request/response messages are added to storage (closest equivalent to pre-write persistence compaction). |
| **Agent-level whole-list compaction (pre-send overlap with post-load)** | `ChatClientAgent` message assembly + chat-client decoration via `clientFactory` / `ChatClientAgentRunOptions.ChatClientFactory` | `ChatClientAgent` builds the full invocation message list (`ChatHistoryProvider` + `AIContextProviders` + input). A delegating `IChatClient` can compact that assembled list immediately before forwarding `GetResponseAsync`. |
| **In-run compaction before every `get_response` call** | Function-invocation chat-client layer (`FunctionInvokingChatClient`) plus delegating `IChatClient` wrapper | The function-calling layer performs repeated model roundtrips; wrapping this layer allows compaction to execute before each `GetResponseAsync` call. |
| **Variant C1 grouped-state maintenance (`MessageGroup`)** | Keep grouped state in the same function-invocation/delegating-chat-client layer | Maintain and update grouped state across loop iterations in that layer, then flatten only for model calls. |
| **Variant C2 message-annotation maintenance (`_group_*`)** | Keep message annotations in the same function-invocation/delegating-chat-client layer | Incrementally annotate newly appended messages with `_group_id`, `_group_kind`, and related metadata; filter/project directly from annotated message lists. |
| **Compaction on existing storage** | `InMemoryChatHistoryProvider.GetMessages(...)` + `SetMessages(...)` (or custom provider equivalent) | Read stored history, apply reducer/strategy, and write back compacted history as a maintenance operation. |

### Coverage Matrix

How each option addresses the three primary compaction points and the current architectural limitations:

| Compaction Point | Option 1 (Strategy) | Option 2 (Mixin) | Option 3 (Provider) | Option 4 (Middleware) |
|-----------------|---------------------|-------------------|---------------------|-----------------------|
| **Pre-write** | ✅ `HistoryProvider` param | ⚠️ Needs extra method | ⚠️ `after_run` override | ❌ Not supported |
| **In-run (tool loop)** | ✅ `FunctionInvocationConfiguration` | ⚠️ Awkward extraction | ⚠️ `isinstance` wiring | ⚠️ Requires refactoring copy semantics |
| **Existing storage** | ✅ Standalone `compact()` | ✅ Provider's `compact()` | ✅ Standalone `compact()` | ❌ Not supported |
| **Solves copy problem** | ✅ Runs inside loop | ⚠️ Indirectly | ⚠️ Indirectly | ⚠️ Requires deep refactor |
| **Chaining** | ✅ Natural composition via wrapper | ❌ Coupled to provider | ⚠️ Boundary only, not in-run | ⚠️ Implicit via stacking |
| **New concepts** | 1 (`CompactionStrategy`) | 1 (mixin) | 0.5 (reuses `ContextProvider`, but adds new method) | 0 (reuses `ChatMiddleware`) |


## Appendix

### Appendix A: Strategy and constraint background

### Compaction Strategies (Examples)

A compaction strategy takes a list of messages and returns a (potentially shorter) list, in almost all cases, there is certain logic that needs to be applied universally, such as retaining system messages, not breaking up function call and result pairs (for Responses that includes Reasoning as well, see [context section above](#message-list-correctness-constraint-atomic-group-preservation) for more info) as tool calls, etc. Beyond that, strategies can be as simple or complex as needed:

- **Truncation**: Keep only the last N messages or N tokens, this is a likely done as a kind of zigzag, where the history grows, then get's truncated to some value below the token limit, then grows again, etc. This can be done on a simple message count basis, a character count basis, or more complex token counting basis.
- **Summarization**: Replace older messages with an LLM-generated summary (depending on the implementation this could be done, by replacing the summarized messages, or by inserting a summary message in between and not loading messages older then the summarized ones)
- **Selective removal**: Remove tool call/result pairs while keeping user/assistant turns
- **Sliding window with anchor**: Keep system message + last N messages
- **Custom logic**: The design should be extendible so that users can implement their own strategies.

### Leveraging Source Attribution

[ADR-0016](./0016-python-context-middleware.md#4-source-attribution-via-source_id) introduces `source_id` attribution on messages — each message tracks which `ContextProvider` added it. Compaction strategies can use this attribution to make informed decisions about what to compact and what to preserve:

- **Preserve RAG context**: Messages from a RAG provider (e.g. `source_id: "rag"`) may be critical and should survive compaction
- **Remove ephemeral context**: Messages marked as ephemeral (e.g., `source_id: "time"`) can be safely removed
- **Protect user input**: Messages without a `source_id` (direct user input) should typically be preserved
- **Selective tool result compaction**: Tool results from specific providers can be summarized while others are kept verbatim

This means strategies don't need to rely solely on message position or role — they can make semantically meaningful compaction decisions based on the origin of each message.

### Appendix B: Additional implementation notes

#### Trigger mechanism for in-run compaction

Running compaction after **every** tool call is wasteful — most iterations the context is well within limits. Instead, compaction should only trigger when a threshold is exceeded. There are several approaches to consider:

1. **Message count threshold**: Trigger when the message list exceeds N messages. Simple to implement and predictable, but message count is a poor proxy for token usage — a single tool result can contain thousands of tokens while counting as one message.

2. **Character/token count threshold**: Trigger when the estimated token count exceeds a budget. More accurate but requires a token counting mechanism (exact tokenization is model-specific and expensive; character-based heuristics like `len(text) / 4` are fast but approximate).

3. **Iteration-based**: Trigger every N tool loop iterations (e.g., every 10th iteration). Predictable cadence but doesn't account for actual context growth — 10 iterations with small results may not need compaction while 3 iterations with large results might.

4. **Strategy-internal**: Let the `CompactionStrategy.compact()` method decide internally — it receives the full message list and can return it unchanged if no compaction is needed. This is the simplest integration point (always call `compact()`, let the strategy no-op when appropriate) but has the overhead of calling into the strategy every iteration.

The recommended approach is **strategy-internal with a lightweight guard**: the `compact()` method is called after each tool result, but strategy implementations should include a fast short-circuit check (e.g., `if len(messages) < self.threshold: return False`) to minimize overhead when compaction is not needed. This keeps the tool loop simple (always call `compact()`) while letting each strategy define its own trigger logic.

The following example illustrates this for Variant A (in-place flat list). See Variant C1/C2 under Option 1 for group-aware equivalents.

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

#### Compaction on pre-write and in-run

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
        used_strategy = strategy or self._get_strategy("existing") or self._get_strategy("pre_write")
        if used_strategy is None:
            raise ValueError("No compaction strategy configured for existing storage.")
        await used_strategy.compact(history)
        await self.replace_messages(session_id, history)  # or save_messages with overwrite
        # or
        await self.save_messages(session_id, history, overwrite=True)
```

This design choice is orthogonal to the compaction strategy options below — any option requires one of these `HistoryProvider` extensions and optionally the convenience method.

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
