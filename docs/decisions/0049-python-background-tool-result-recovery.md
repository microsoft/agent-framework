---
status: proposed
contact: sophia-ramsey
date: 2026-11-04
deciders: sophia-ramsey, eavanvalkenburg
---

# Session-backed background tool-result recovery

## Context and Problem Statement

In [#9031](https://github.com/microsoft/agent-framework/issues/9031), polling an OpenAI background response can
execute local tools before submitting their results fails. Retrying the application's original continuation token
retrieves the same calls and repeats side effects. Successful-run history hooks cannot retain the results of a run
that raised an exception.

## Decision Drivers

- Never repeat completed local actions merely to retry result delivery.
- Preserve occurrence identities, ordered transcripts, reasoning, middleware semantics, and consumed invocation budgets.
- Fail explicitly when execution or provider acceptance is uncertain.
- Keep recovery scoped to Responses background operations, not a general durable execution engine or the mixed
  approval/Host result-delivery work tracked by [#8574](https://github.com/microsoft/agent-framework/issues/8574).

## Considered Options

- Remove only the loop-owned continuation token: preserves compatibility, but does not protect later caller retries.
- Cache results on the client instance: simple, but shares ownership across sessions and loses evidence on restoration.
- Retain execution and delivery evidence in the caller's session: survives explicit serialization and separates tool
  execution from result delivery, but requires caller-retained state and serialized session ownership.
- Distributed durable outbox and provider idempotency: stronger coordination, but needs external infrastructure and
  provider guarantees outside this fix.

## Decision Outcome

Chosen option: session-backed recovery. The shared function loop claims each local occurrence before invoking its
middleware or tool and saves each completed result separately. A versioned checkpoint retains the exact prepared
delivery messages, transcript, original input, usage, and portable invocation budget. Message and content snapshots
are opaque JSON so session restoration does not reinterpret their nested serialization discriminators.

The shared OpenAI Responses adapter supplies a provider/endpoint/model/organization/project scope and declares the
recovery state as provider-owned, including for inherited Azure OpenAI and Foundry clients. Ordinary foreground calls
and other provider protocols do not opt into this recovery path.

### Recovery lifecycle

Retry with the same token, original input, and session bypasses retrieval and function invocation, submitting the
retained results against their original response. The pending record follows these transitions:

| Current state | Trigger | Next state | Required invariant |
|---|---|---|---|
| No pending record | `start_call()` claims the first local occurrence | `executing` | Record the claim before invoking function middleware or the tool body. |
| `executing` | `complete_call()` records one completed occurrence | `executing` | Save each result independently, including when siblings are still running. |
| `executing` | `checkpoint()` captures the complete batch | `ready` | Every claimed occurrence has a result; prepared messages, transcript, usage, and budget are retained. |
| `ready` | `restore()` prepares a retry | `ready` | Reuse the retained delivery messages; do not retrieve or execute the completed calls again. |
| `ready` | `before_request()` begins result submission | `submitting` | Record submission before calling the provider. |
| `submitting` | `observe_response()` receives a successful provider response | No pending record | Retain consumed response identities before clearing the pending results. |
| `submitting` | HTTP 429 or 503 occurs before any submission-stream update | `ready` | Permit another delivery attempt using the same retained results. |
| `executing` | Execution exits with an exception or cancellation | `indeterminate` | Preserve completed siblings; never replay the batch blindly. |
| `submitting` | Any other failure, or a failure after a submission-stream update | `indeterminate` | Require reconciliation rather than assuming the provider did not accept the request. |
| `ready` | An exception or stream close occurs before submission begins | `ready` | Keep the delivery checkpoint available; no new submission has started. |
| Any pending state | The run exits successfully without an exception | No pending record | Retain consumed identities, including for an early terminal return; this alone is not proof of provider acceptance. |

There is no stored `settled` status: settlement clears the pending record while retaining the handled-response ledger.
Observing a submission-stream update does not change `submitting`, but makes a later failure non-retryable. Invalid
checkpoints and attempts to resume an `indeterminate` record fail before delivery. Retrying delivery does not guarantee
exactly-once processing of model requests by the provider.

The session's `busy` flag is separate from the pending state. The coordinator claims it when the attempt is consumed
and releases it when that attempt exits; it is not a distributed lock for separately restored session copies.

### Compatibility and replay protection

Successful result delivery retains consumed response identities so old tokens cannot reopen completed executions.
The bounded ledger refuses further background tool execution when full rather than evicting protective evidence.
Concurrent polls against one live session are rejected. Stateless background calls that would automatically execute
tools are rejected before invoking tool middleware or bodies; callers must retain an explicit `AgentSession`.
Pending delivery rejects new input or a different provider/model instead of silently abandoning results.

### Preserved behavior and non-goals

Both response modes reconstruct the same complete transcript on recovery, including occurrence IDs and reasoning.
Streaming recovery can repeat previously exposed updates; it does not promise exactly-once delivery to a UI.
Existing approval, Host-pause, fatal middleware, and provider-invalidation rules remain in force. Calls replayed during
the initial approval/Host resolution phase retain their existing contract, not this new background-poll checkpoint;
their result-delivery recovery remains the separate #8574 work. Incomplete or unsupported background-poll recovery
fails closed rather than inventing approval authority.

### Host responsibilities

Applications must persist the session after failed attempts, protect stored results as sensitive application state,
and serialize ownership across restored workers. Session mutation is not an automatic disk checkpoint, an external
transaction, or a distributed lock. A crash between an external side effect and durable state storage still requires
application-level reconciliation or tool idempotency.