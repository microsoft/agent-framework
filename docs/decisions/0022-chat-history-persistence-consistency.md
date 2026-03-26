---
status: accepted
contact: westey-m
date: 2026-03-23
deciders: sergeymenshykh, markwallace, rbarreto, dmytrostruk, westey-m, eavanvalkenburg, stephentoub
consulted:
informed:
---

# Chat History Persistence Consistency

## Context and Problem Statement

When using `ChatClientAgent` with tools, the `FunctionInvokingChatClient` (FIC) loops multiple times — service call → tool execution → service call → … — before producing a final response. There are two points of discrepancy between how chat history is stored by the framework's `ChatHistoryProvider` and how the underlying AI service stores chat history (e.g., OpenAI Responses with `store=true`):

1. **Persistence timing**: The AI service persists messages after *each* service call within the FIC loop. The `ChatHistoryProvider` currently persists messages only once, at the *end* of the full agent run (after all FIC loop iterations complete).

2. **Trailing `FunctionResultContent` storage**: When tool calling is terminated mid-loop (e.g., via `FunctionInvokingChatClient` termination filters), the final response from the agent may contain `FunctionResultContent` that was never sent to a subsequent service call. The AI service never stores this trailing `FunctionResultContent`, but the `ChatHistoryProvider` currently stores all response content, including the trailing `FunctionResultContent`.

These discrepancies mean that a `ChatHistoryProvider`-managed conversation and a service-managed conversation can diverge in content and structure, even when processing the same interactions.

### Practical Impact: Resuming After Tool-Call Termination

Today, users of `AIAgent` get different behaviors depending on whether chat history is stored service-side or in a `ChatHistoryProvider`. This creates concrete challenges — for example, when the function call loop is terminated and the user wants to resume the conversation in a subsequent run. With service-stored history, the trailing `FunctionResultContent` is never persisted, so the last stored message is the `FunctionCallContent` from the service. With `ChatHistoryProvider`-stored history, the trailing `FunctionResultContent` *is* persisted. The user cannot know whether the last `FunctionResultContent` is in the chat history or not without inspecting the storage mechanism, making it difficult to write resumption logic that works correctly regardless of the storage backend.

### Relationship Between the Two Discrepancies

The persistence timing and `FunctionResultContent` trimming behaviors are interrelated:

- **Per-service-call persistence**: When messages are persisted after each individual service call, trailing `FunctionResultContent` trimming is unnecessary. If tool calling is terminated, the `FunctionResultContent` from the terminated call was never sent to a subsequent service call, so it is never persisted. The per-service-call approach naturally matches the service's behavior.

- **Per-run persistence**: When messages are batched and persisted at the end of the full run, trailing `FunctionResultContent` trimming becomes necessary to match the service's behavior. Without trimming, the stored history contains `FunctionResultContent` that the service would never have stored.

This means the trimming feature (introduced in [PR #4792](https://github.com/microsoft/agent-framework/pull/4792)) is primarily needed as a complement to per-run persistence. The `PersistChatHistoryAtEndOfRun` setting (introduced in [PR #4762](https://github.com/microsoft/agent-framework/pull/4762)) inverts the default so that per-service-call persistence is the standard behavior, and per-run persistence is opt-in.

## Decision Drivers

- **A. Consistency**: The default behavior of `ChatHistoryProvider` should produce stored history that closely matches what the underlying AI service would store, minimizing surprise when switching between framework-managed and service-managed chat history.
- **B. Atomicity**: A run that fails mid-way through a multi-step tool-calling loop should not leave chat history in a partially-updated state, unless the user explicitly opts into that behavior.
- **C. Recoverability**: For long-running tool-calling loops, it should be possible to recover intermediate progress if the process is interrupted, rather than losing all work from the current run.
- **D. Simplicity**: The default behavior should be easy to understand and predict for most users, without requiring knowledge of the FIC loop internals.
- **E. Flexibility**: Regardless of the chosen default, users should be able to opt into the alternative behavior.

## Considered Options

- Option 1: Default to per-run persistence with `FunctionResultContent` trimming (opt-in to per-service-call)
- Option 2: Default to per-service-call persistence (opt-in to per-run)

## Pros and Cons of the Options

### Option 1: Default to per-run persistence with `FunctionResultContent` trimming

Keep the current default behavior of persisting chat history only at the end of the full agent run. Add `FunctionResultContent` trimming as the default to improve consistency with service storage. Provide an opt-in setting for users who want per-service-call persistence.

Settings:
- `PersistChatHistoryAtEndOfRun` = `true`

- Good, because runs are atomic — chat history is only updated when the full run succeeds, satisfying driver B.
- Good, because the mental model is simple: one run = one history update, satisfying driver D.
- Good, because trimming trailing `FunctionResultContent` improves consistency with service storage, partially satisfying driver A.
- Good, because users can opt in to per-service-call persistence for checkpointing/recovery scenarios, satisfying drivers C and E.
- Bad, because the default persistence timing still differs from the service's behavior (per-run vs. per-service-call), only partially satisfying driver A.
- Bad, because if the process crashes mid-loop, all intermediate progress from the current run is lost, not satisfying driver C by default.

### Option 2: Default to per-service-call persistence

Change the default to persist chat history after each individual service call within the FIC loop, matching the AI service's behavior. Trailing `FunctionResultContent` trimming is unnecessary with this approach (it is naturally handled). Provide an opt-in setting for users who want per-run atomicity with trimming.

Settings:
- `PersistChatHistoryAtEndOfRun` = `false` (default)

- Good, because the stored history matches the service's behavior by default for both timing and content, fully satisfying driver A.
- Good, because intermediate progress is preserved if the process is interrupted, satisfying driver C.
- Good, because no separate `FunctionResultContent` trimming logic is needed, reducing complexity.
- Bad, because chat history may be left in an incomplete state if the run fails mid-loop (e.g., `FunctionCallContent` stored without corresponding `FunctionResultContent`), not satisfying driver B. A subsequent run cannot proceed without manually providing the missing `FunctionResultContent`.
- Bad, because the mental model is more complex: a single run may produce multiple history updates, partially failing driver D.
- Neutral, because users can opt out to per-run persistence if they prefer atomicity, satisfying driver E.

## Decision Outcome

Chosen option: **Option 2 — Default to per-service-call persistence**, because it fully satisfies the consistency driver (A), naturally handles `FunctionResultContent` trimming without additional logic, and provides better recoverability for long-running tool-calling loops. Per-run persistence remains available via the `PersistChatHistoryAtEndOfRun` setting for users who prefer atomic run semantics.

### Configuration Matrix

The behavior depends on the combination of `UseProvidedChatClientAsIs` and `PersistChatHistoryAtEndOfRun`:

| `UseProvidedChatClientAsIs` | `PersistChatHistoryAtEndOfRun` | Behavior |
|---|---|---|
| `false` (default) | `false` (default) | **Per-service-call persistence.** A `ChatHistoryPersistingChatClient` middleware is automatically injected into the chat client pipeline between `FunctionInvokingChatClient` and the leaf `IChatClient`. Messages are persisted after each service call. |
| `true` | `false` | **User responsibility.** No middleware is injected because the user has provided a custom chat client stack. The user is responsible for ensuring correct persistence behavior (e.g., by including their own persisting middleware). |
| `false` | `true` | **Per-run persistence with marking.** A `ChatHistoryPersistingChatClient` middleware is injected, but configured to *mark* messages with metadata rather than store them immediately. At the end of the run, marked messages are stored. Trailing `FunctionResultContent` is trimmed. |
| `true` | `true` | **Per-run persistence with warning.** The system checks whether the custom chat client stack includes a `ChatHistoryPersistingChatClient`. If not, a warning is emitted (particularly relevant for workflow handoff scenarios where trimming cannot be guaranteed). If no `ChatHistoryPersistingChatClient` is preset, all messages are stored at the end of the run, otherwise marked messages are stored. |

### Consequences

- Good, because the stored history matches the service's behavior by default for both timing and content, fully satisfying consistency (driver A).
- Good, because intermediate progress is preserved if the process is interrupted, satisfying recoverability (driver C).
- Good, because no separate `FunctionResultContent` trimming logic is needed in the default path, reducing complexity.
- Good, because marking persisted messages with metadata enables deduplication and aids debugging.
- Good, because warnings for custom chat client configurations without the persisting middleware help prevent silent failures in workflow handoff scenarios.
- Bad, because chat history may be left in an incomplete state if the run fails mid-loop (e.g., `FunctionCallContent` stored without corresponding `FunctionResultContent`), requiring manual recovery in rare cases.
- Bad, because the mental model is more complex for the default path: a single run may produce multiple history updates.
- Neutral, because users who prefer atomic run semantics can opt in to per-run persistence via `PersistChatHistoryAtEndOfRun = true`.
- Neutral, because increased write frequency from per-service-call persistence may impact performance for some storage backends; this can be mitigated with a caching decorator.

### Implementation Notes

#### Conversation ID Consistency

The `ChatHistoryPersistingChatClient` middleware must also update the session's `ConversationId` consistently for both response-based and conversation-based service interactions, ensuring the session always reflects the latest service-provided identifier.

## More Information

- [PR #4762: Persist messages during function call loop](https://github.com/microsoft/agent-framework/pull/4762) — introduces `PersistChatHistoryAfterEachServiceCall` option and `ChatHistoryPersistingChatClient` decorator
- [PR #4792: Trim final FRC to match service storage](https://github.com/microsoft/agent-framework/pull/4792) — introduces `StoreFinalFunctionResultContent` option and `FilterFinalFunctionResultContent` logic
- [Issue #2889](https://github.com/microsoft/agent-framework/issues/2889) — original issue tracking chat history persistence during function call loops
