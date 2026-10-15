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

The proposed deciders are Python code owners; maintainer and
engineering-management approval is still required.
