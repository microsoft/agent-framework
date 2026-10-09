---
status: proposed
contact: westey-m
date: 2026-10-02
deciders: westey-m
---

# Reject unanswered tool approvals on the next .NET agent run

## Context and Problem Statement

An agent can save a tool-approval request and return it to an app that never sends
an answer. The user might close the page or the app might fail before submitting
the decision. Later messages then fail because the saved conversation contains
an unanswered request. Retrying a previously supplied answer is supported, but
does not help an app that no longer holds that answer.

See [microsoft/agent-framework#8849](https://github.com/microsoft/agent-framework/issues/8849)
and the earlier [approval design](0006-userapproval.md).

## Decision Drivers

- A missing answer must never authorize tool execution.
- A conversation should remain usable after the app loses an approval request.
- Supplied decisions and retry behavior should keep working.
- Recovery should work with a saved and restored session.

## Considered Options

- Continue throwing until the app supplies every answer.
- Return the unanswered approval requests to the caller again.
- Automatically reject unanswered requests on the next run.

## Decision Outcome

Chosen option: **automatically reject unanswered requests on the next run**.
This allows the conversation to continue without executing tools the user did
not approve. Returning requests again complicates the response and history
handling, while continuing to throw leaves the reported problem unresolved.

The existing `ApprovalResponseBindingChatClient` first checks supplied answers,
then supplies a rejection for each remaining saved request whose call does not
already have a result. This applies to partially answered batches and empty
input, not just new text messages. Waiting or closing the app does not itself
reject anything; the app must start another run.

Use the saved request's tool call, not a caller-supplied replacement. Keep the
existing protection against fabricated and duplicate approvals, and the
existing removal of pending state only after the inner call succeeds. A failed
attempt therefore leaves requests available for retry.

Copy both incoming approval calls and the saved calls used to make decisions:
the function-invocation code changes those call objects while handling them.
A failed attempt must not change the original request or prevent a later explicit
approval from executing the tool.

Group supplied, automatic, and missing-answer decisions after any replayed
requests and before new caller content. This keeps the resulting tool results
before the new question, including when the inference service owns the history.

Return the generated rejection responses before the tool-call/result messages,
so callers can see the decisions and end-of-run history saving can store them.
Do not return supplied answers again: they are already part of the input.
Keep the returned function-call objects separate from the ones processed by
the function-invocation code, so their flags are not changed during processing.
Service-side and per-service-call history saving still happens below that code
and receives only the processed function calls/results, not approval content.
Streaming emits the generated decisions before the tool results; a later failure
or early stop still leaves the saved approval requests available for retry.
Receiving a streamed decision is not proof that the whole run succeeded.

When incoming history already contains a result for a call, preserve its approval
response without requiring a pending session record and do not generate another
rejection. The function-invocation code uses that result to avoid processing the
call again. History containing an approval request and a result but no matching
approval response is not repaired by this component; the request still needs
an answer. Returning generated responses ensures newly saved conversations
include that answer without changing the original request's flags.
No additional history read is required.

Workflow hosts also forward externally supplied approval answers before the
agent's tool results, even when ordinary incoming messages are not forwarded.
Other agents may already have received the approval request as part of the
shared conversation; forwarding only its result would leave that request
unanswered in their histories. This forwarding applies only to answers handled
by the workflow's approval-response handler, not decisions received from other
agents.

This is the default where approval-response binding is enabled. Disabling that
component also disables automatic rejection; no separate setting is added.
Tools that do not require approval keep their existing automatic handling.
The helper that presents requests one at a time keeps its queue behavior: this
rule applies when it next calls the underlying agent.

Apps must supply all desired approval decisions before continuing the agent.
An answer arriving after a successful automatic rejection cannot authorize the
old call. The model can still request a new call and ask for approval again.
This decision does not make tool execution and history storage a single atomic
operation or remove the existing possibility of repeated execution after a
failed run.

In particular, a service may accept a tool result during one call before a later
call in the same run fails. The outer approval checker cannot observe that
intermediate success, and service-owned history may not be readable. Retrying
can therefore send another result, either by repeating an explicit approval or
by rejecting an unanswered request. Avoiding this requires separate handling of
partial service success; this decision does not add approval-specific tracking
to the history-persistence component.
