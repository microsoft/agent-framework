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

## Decision Drivers

- **A. Consistency**: The default behavior of `ChatHistoryProvider` should produce stored history that closely matches what the underlying AI service would store, minimizing surprise when switching between framework-managed and service-managed chat history.
- **B. Atomicity**: A run that fails mid-way through a multi-step tool-calling loop should not leave chat history in a partially-updated state, unless the user explicitly opts into that behavior.
- **C. Recoverability**: For long-running tool-calling loops, it should be possible to recover intermediate progress if the process is interrupted, rather than losing all work from the current run.
- **D. Simplicity**: The default behavior should be easy to understand and predict for most users, without requiring knowledge of the FIC loop internals.
- **E. Flexibility**: Regardless of the chosen default, users should be able to opt into the alternative behavior.

## Considered Options

- Option 1: Per-run persistence with opt-in FRC (FunctionResultContent) trimming
- Option 2: Opt-in per-service-call persistence (via `RequirePerServiceCallChatHistoryPersistence`)

## Pros and Cons of the Options

### Option 1: Per-run persistence with opt-in FRC trimming

Keep the current default behavior of persisting chat history only at the end of the full agent run. Add `FunctionResultContent` trimming as an opt-in behavior to improve consistency with service storage.

- Good, because runs are atomic — chat history is only updated when the full run succeeds, satisfying driver B.
- Good, because the mental model is simple: one run = one history update, satisfying driver D.
- Good, because trimming trailing `FunctionResultContent` improves consistency with service storage, partially satisfying driver A.
- Bad, because the default persistence timing still differs from the service's behavior (per-run vs. per-service-call), only partially satisfying driver A.
- Bad, because if the process crashes mid-loop, all intermediate progress from the current run is lost, not satisfying driver C.
- Bad, because this option alone does not provide a way for users to opt into per-service-call persistence, not satisfying driver E.

### Option 2: Opt-in per-service-call persistence (via `RequirePerServiceCallChatHistoryPersistence`)

Introduce an optional RequirePerServiceCallChatHistoryPersistence setting to persist chat history after each individual service call within the FIC loop, matching the AI service's behavior. Trailing `FunctionResultContent` trimming is unnecessary with this approach (it is naturally handled).

Settings:
- `RequirePerServiceCallChatHistoryPersistence` = `true`

- Good, because the stored history matches the service's behavior when opting in for both timing and content, fully satisfying driver A.
- Good, because intermediate progress is preserved if the process is interrupted, satisfying driver C.
- Good, because no separate `FunctionResultContent` trimming logic is needed, reducing complexity.
- Bad, because chat history may be left in an incomplete state if the run fails mid-loop (e.g., `FunctionCallContent` stored without corresponding `FunctionResultContent`), not satisfying driver B. A subsequent run cannot proceed without manually providing the missing `FunctionResultContent`.
- Bad, because the mental model is more complex: a single run may produce multiple history updates, partially failing driver D.
- Neutral, because users can opt out to per-run persistence if they prefer atomicity, satisfying driver E.

## Decision Outcome

Chosen option: **Option 2: Opt-in per-service-call persistence (via `RequirePerServiceCallChatHistoryPersistence`)**. The existing per-run persistence behavior is retained as-is, requiring no changes from users. Per-service-call persistence is available as an opt-in feature via the `RequirePerServiceCallChatHistoryPersistence` setting. This satisfies drivers B (atomicity) and D (simplicity) for the common case, while fully satisfying driver A (consistency) for users who opt into simulated service-stored behavior. Users who need per-service-call persistence for recoverability (driver C) can enable it explicitly.

### Configuration Matrix

The behavior depends on the combination of `UseProvidedChatClientAsIs` and `RequirePerServiceCallChatHistoryPersistence`:

| `UseProvidedChatClientAsIs` | `RequirePerServiceCallChatHistoryPersistence` | Behavior |
|---|---|---|
| `false` (default) | `false` (default) | **Per-run persistence.** Messages are persisted at the end of the full agent run via the `ChatHistoryProvider`. |
| `false` | `true` | **Per-service-call persistence (simulated).** A `PerServiceCallChatHistoryPersistingChatClient` middleware is automatically injected into the chat client pipeline between `FunctionInvokingChatClient` and the leaf `IChatClient`. Messages are persisted after each service call. A sentinel `ConversationId` causes FIC to treat the conversation as service-managed. |
| `true` | `false` | **Per-run persistence.** No middleware is injected because the user has provided a custom chat client stack. Messages are persisted at the end of the run. |
| `true` | `true` | **User responsibility.** The system checks whether the custom chat client stack includes a `PerServiceCallChatHistoryPersistingChatClient`. If not, a warning is emitted — the user is expected to have added their own per-service-call persistence mechanism. End-of-run persistence is skipped. |

### Consequences

- Good, because per-run persistence is atomic by default — chat history is only updated when the full run succeeds, satisfying driver B.
- Good, because the default mental model is simple: one run = one history update, satisfying driver D.
- Good, because users who opt into `RequirePerServiceCallChatHistoryPersistence` get stored history that matches the service's behavior for both timing and content, fully satisfying driver A.
- Good, because per-service-call persistence preserves intermediate progress if the process is interrupted, satisfying driver C when opted in.
- Good, because no separate `FunctionResultContent` trimming logic is needed when per-service-call persistence is active — it is naturally handled.
- Good, because conflict detection (configurable via `ThrowOnChatHistoryProviderConflict`, `WarnOnChatHistoryProviderConflict`, `ClearOnChatHistoryProviderConflict`) prevents misconfiguration when a service returns a `ConversationId` alongside a configured `ChatHistoryProvider`.
- Bad, because per-service-call persistence (when opted in) may leave chat history in an incomplete state if the run fails mid-loop (e.g., `FunctionCallContent` stored without corresponding `FunctionResultContent`), requiring manual recovery in rare cases.
- Neutral, because users who want per-service-call consistency can opt in via `RequirePerServiceCallChatHistoryPersistence = true`, satisfying driver E.
- Neutral, because increased write frequency from per-service-call persistence may impact performance for some storage backends; this can be mitigated with a caching decorator.

### Implementation Notes

#### Conversation ID Consistency

When `RequirePerServiceCallChatHistoryPersistence` is enabled, the `PerServiceCallChatHistoryPersistingChatClient`
decorator also updates `session.ConversationId` after each service call. This handles two scenarios:

1. **Framework-managed chat history** — the decorator sets a sentinel `ConversationId` on the response
   so that `FunctionInvokingChatClient` treats the conversation as service-managed (clearing accumulated
   history between iterations and not injecting duplicate `FunctionCallContent` during approval processing).

2. **Service-stored chat history** — when the service returns a real `ConversationId`, the decorator
   updates `session.ConversationId` immediately after each service call, rather than deferring the update
   to the end of the run. This ensures intermediate ConversationId changes are captured even if the
   process is interrupted mid-loop.

For some service-stored scenarios (e.g., the Conversations API with the Responses API), there is only
one thread with one ID, so every service call returns the same ConversationId and this per-call update
makes no practical difference. Enabling `RequirePerServiceCallChatHistoryPersistence` ensures consistent
per-service-call behavior across all service types regardless of how they manage ConversationIds.

