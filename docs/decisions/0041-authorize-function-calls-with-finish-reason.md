---
status: proposed
contact: eavanvalkenburg
date: 2026-09-11
deciders: eavanvalkenburg
---

# Authorize function calls with the finish reason

## Context and Problem Statement

Streaming providers expose function-call content before they commit the complete model turn. Agent Framework already
waits for the provider stream to finish before local invocation, but iterator completion alone does not prove that the
provider emitted its terminal event or committed every call. A syntactically complete call fragment can therefore be
mistaken for an executable request after an interrupted or failed response.

## Decision Drivers

- Execute local side effects only after an authoritative provider completion signal.
- Keep one provider-neutral authorization rule for streaming and non-streaming responses.
- Preserve incremental function-call updates for callers without adding buffering or another stream drain.
- Avoid adding a second response lifecycle field or changing the meaning of `informational_only`.
- Keep provider-specific protocol evidence in the provider adapter.

## Considered Options

### Add a response completion field

- Good: separates lifecycle state from generation finish reason.
- Bad: adds a public concept that overlaps existing finish-reason behavior.
- Bad: requires every response and update mapping to carry another field.

### Mark speculative calls as informational

- Good: reuses the existing core execution filter.
- Bad: `informational_only` describes calls the framework does not own, not uncommitted local calls.
- Bad: changes the meaning of caller-visible function-call content.

### Infer commitment from content or stream exhaustion

- Good: requires no provider changes.
- Bad: complete JSON and clean iterator exhaustion do not prove that the provider committed the turn.
- Bad: different providers expose different authoritative terminal events.

### Authorize with `finish_reason == "tool_calls"`

- Good: uses the existing provider-neutral response field.
- Good: gives core one fail-closed rule for streaming and non-streaming responses.
- Good: lets providers continue yielding speculative content immediately and resolve the reason on their existing
  terminal event.
- Bad: custom clients that return local function calls without `finish_reason="tool_calls"` must be updated.
- Bad: provider adapters must assign `"tool_calls"` only after their own protocol commitment evidence is satisfied.

## Decision Outcome

Chosen option: "Authorize with `finish_reason == "tool_calls"`", because it establishes one explicit execution
boundary without another public lifecycle model.

Core approves or executes model-issued local calls only when the finalized response has
`finish_reason == "tool_calls"`. Missing and all other finish reasons are non-authorizing.

Each provider adapter owns its commitment evidence. Adapters that require correction use the same small local
`_resolve_finish_reason(...)` pattern: committed calls override the ordinary reason to `"tool_calls"`; calls without
commitment cannot retain or manufacture `"tool_calls"`; responses without calls preserve their ordinary reason. The
function remains local to each provider module because the evidence is protocol-specific and does not justify a shared
base class, mixin, registry, or cross-provider helper.

Streaming adapters resolve the finish reason on the provider's existing terminal event. They do not add another drain,
buffer speculative content, or wait after iterator exhaustion. Calls returned without authorization remain visible to
the caller but are excluded from later model-bound replay.

### Consequences

- Local tool bodies, approval requests, function middleware, function results, and follow-up model calls require an
  authoritatively committed `"tool_calls"` response.
- Custom clients must set `finish_reason="tool_calls"` for completed local function-call turns.
- Provider adapters must not infer commitment from parseable arguments, observed call content, or iterator exhaustion.
- Interrupted call-bearing responses remain inspectable without becoming executable or replayable model history.
