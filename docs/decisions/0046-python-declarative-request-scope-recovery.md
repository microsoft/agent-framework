---
status: proposed
contact: baywet
date: 2026-10-15
deciders: eavanvalkenburg, westey-m
---

# Preserve declarative request origins with opt-in legacy recovery

## Context and Problem Statement

A declarative workflow can retain requests from several fresh runs. Resuming a
question, tool approval, or agent external-input request must restore its
originating workflow scope rather than inherit the most recent run's MCP session.
Older checkpoints do not retain that origin, so the framework cannot infer which
session should be resumed.

## Decision Drivers

- All declarative pause types need the same origin and response-batch rules.
- Existing checkpoints need an explicit recovery path without guessing an origin.
- Repeated restoration must select the same migrated scope without sharing a newer run's session.

## Considered Options

- Use the current workflow scope for requests without an origin. This needs no
  host changes and retains apparent continuity, but can attach an older request
  to an unrelated fresh run.
- Reject all unknown origins and require restarting the workflow. This avoids
  guessing, but prevents hosts from recovering otherwise usable pending requests.
- Automatically assign isolated scopes. This permits recovery without host
  changes, but silently loses the previous MCP session's server-side state.
- Require explicit host opt-in to assign stable, isolated scopes. This makes the
  continuity trade-off visible and permits recovery, but requires host changes
  and separate resumes for legacy requests.

## Decision Outcome

Choose explicit host opt-in through
`WorkflowFactory(migrate_legacy_request_scopes=True)`, defaulting to `False`:

- Questions/external input, function approvals, MCP approvals, and agent external
  input retain their originating scope in the request. Response handlers restore
  it before continuing. Agent requests also retain their own loop configuration.
- Factory-built workflows validate all submitted request origins before consuming
  responses. Mixed-scope batches are rejected without changing request metadata.
- Checkpoint restores validate queued response origins before restoring shared or
  executor state, including embedded child checkpoints. Submitted and already
  queued responses share the same batch validation before pending requests are consumed.
- Nested restoration preflights a detached copy of the complete embedded tree
  with each child's own policy before applying live state or queues. Migration
  metadata is confined to that candidate; a rejected child leaves earlier
  siblings, parent executors, and the supplied checkpoint unchanged.
- Without opt-in, a missing origin produces an actionable recovery error.
- With opt-in, a missing origin becomes
  `legacy-request:<framework request ID>`. The distinct namespace never selects
  the active run's scope; preserving the request ID makes migration stable across
  workers and repeated restoration. Legacy requests must be resumed separately.
- Existing valid origins are unchanged. Invalid stored origins are not migrated.
  Migration does not change header verification or authorize an unverifiable
  MCP header context.
- Newly emitted requests and subsequent checkpoints retain the migrated scope.
  The old MCP session and its server-side history cannot be reconstructed.
  Hosts requiring that continuity must restart rather than opt in.
- Legacy agent loop configuration remains available from its old checkpoint
  slot; new requests own their configuration instead of replacing shared state.

Checkpoint contents and framework request IDs remain trusted host-owned data.
Migration does not reconstruct state already overwritten in a legacy checkpoint.
This is a checkpoint-compatibility change with an explicit recovery path, not
transparent restoration of an old session.

## Nested entry checkpoint replay

Selecting a random child scope only when the child first executes is insufficient:
the parent's entry checkpoint predates that selection. Rebuilding the graph and
replaying that checkpoint would select a different child scope. Pre-seeding every
descendant's mutable state before the parent snapshot would instead couple parent
checkpoint creation to child initialization.

Select a parent scope before its entry checkpoint and derive each child scope from
that scope and the binding ID. Agent turns select a stable scope for their session;
direct fresh runs select new scopes. Declarative response handlers restore the
originating parent scope before further nested invocation. Child scope selection
occurs only after the child accepts a fresh run, not before checkpoint validation
or on response-only continuations.

Declarative executors manually composed with Core `WorkflowBuilder` read the
active Core scope instead of reusing a stale declarative cache. Factory
initialization still selects its existing declarative scopes before the entry
checkpoint; standalone state helpers retain their previous initialization behavior.
Restored request scopes take precedence over inherited metadata from later runs.

Older parent checkpoints without this scope cannot reconstruct a child's original
scope if that child had not started. Such parents receive a new isolated scope
with a warning; subsequent checkpoints retain it. Existing request-origin
validation and explicit legacy-request migration rules are unchanged.

## Nested response boundaries

Restoring only a child's scope leaves its ancestors on a later fresh run's scope.
If runs A and B pause in the same child and B is answered before A, a downstream
binding could therefore select B's MCP session while processing A's continuation.

Retain the originating parent run context for each forwarded child request in
framework-owned parent shared state. Unlike transient wrapper fields, this state
is checkpointed with its owning workflow, including at every embedded boundary.
After a child successfully resumes or cancels a request, restore the saved parent
context before forwarding outputs or capturing the origins of follow-up requests.
Release completed origins, preserve still-pending origins across new inputs, and
reject mixed-parent-scope response batches before consuming any requests, including
batches spanning sibling bindings. Cancellation batches obey the same parent-scope
rule because cancellation can also produce downstream outputs.
Checkpoint preflight applies the same validation
to queued propagated and wrapped replies before replacing live state.

Older checkpoints without boundary origins cannot reconstruct those ancestors'
original scopes. A successful child continuation therefore receives a new isolated
parent scope with a warning rather than reusing the latest parent's session.
This does not bypass the child's declarative request-origin checks or explicit
legacy-request migration policy.

## Ordinary Core requests and live response preflight

Ordinary `WorkflowContext.request_info()` requests can also pause before a child
binding. Capturing only forwarded child requests leaves these continuations on the
latest fresh run's scope. Capture their framework-owned run metadata in the same
checkpointed state, and restore it before Core invokes the response handler,
including for queued checkpoint replies. Core cancellation handlers restore the
same metadata. Propagated child responses use this path once; wrapped child
messages retain their boundary-specific capture and restoration.

Preflight includes both propagated responses and wrapped child replies already
queued for delivery. Route wrapped replies through the parent graph to validate
their child's own policy without treating child scopes as parent-policy scopes.
Repeat validation before each live message batch is drained, so a rejected batch
retains its queued replies. Cancellation validates queued replies together with
the complete selected cancellation set before consuming requests or invoking
cancellation handlers. Legacy runner contexts use a non-persisting snapshot when
optional queued-message inspection is unavailable.

Deep-copying all live request payloads to preflight migrations imposes an unrelated
serialization requirement on non-checkpointed, in-process workflows. Instead,
response policies validate without mutation and return deferred updates to the
scope metadata they own. Apply these updates only after every policy in the tree
has validated. This preserves cross-child rejection atomicity without copying user
payloads or changing their identity. Stored checkpoint restoration still preflights
its detached candidate tree before replacing live state.

The proposed deciders are Python code owners; maintainer and
engineering-management approval is still required.
