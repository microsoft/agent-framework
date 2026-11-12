---
status: proposed
contact: baywet
date: 2026-10-28
deciders: westey-m
---

# Explicit ownership for .NET declarative Local state

## Context and Problem Statement

Declarative `Local` and `Topic` variables share canonical `Local` storage and a sensitivity sidecar. Older
checkpoints can instead contain declarative values in physical `Topic` storage. Code-first executors can also use
physical `Topic` independently, including the same key as a declarative variable.

Sensitivity metadata alone cannot identify which physical value it describes. A preflight check cannot prevent
this ambiguity when different fan-out executors queue raw `Topic` and canonical `Local` writes in the same
superstep: each executor sees only its own pending updates.

## Decision Drivers

- Preserve unrelated code-first state and the native representation of canonical values.
- Continue reading and selectively migrating older checkpoints without guessing assignment order.
- Keep declarative storage conventions out of the language-neutral workflow state manager.
- Avoid full-scope scans for individual reads and writes.
- Preserve read-only expression snapshots and the existing checkpoint restoration publication boundary.

## Considered Options

### Infer ownership from sensitivity metadata and visible keys

Good: no additional persisted metadata or core API changes.
Bad: executor-private pending updates defeat the preflight, and committed sensitivity metadata cannot distinguish
canonical ownership from an older declarative `Topic` value.

### Validate combined updates before publication

Good: a validator can inspect updates from every executor before they are committed.
Bad: this needs a new language-neutral validation extension point or declarative scope knowledge in core
publication. Rejecting every same-key pair would also prevent independently owned raw and canonical values.

### Persist versioned canonical ownership separately

Good: plain helpers, wrapped contexts, and restoration can distinguish ownership after concurrent publication,
without changing native values or public workflow APIs.
Bad: writes and checkpoints include one additional private entry per canonical Local key. Older runtimes do not
understand that ownership when both physical scopes contain the same key.

## Decision Outcome

Chosen option: "Persist versioned canonical ownership separately", because the ambiguity belongs to declarative
storage interpretation and does not require changing core publication semantics.

For each new canonical `Local` assignment or migrated legacy entry, persist integer version `1` under the same key
in the private `__Microsoft_Agents_AI_Workflows_Declarative_Ownership:Local` scope, alongside the existing value and
sensitivity sidecar. No ownership entry is needed for other scopes.

A recognized ownership entry means the sensitivity sidecar describes canonical `Local` state. Any same-key raw
`Topic` value remains independent and must not be read as a legacy value, migrated, or deleted by declarative
helpers or restoration. This permits mixed fan-out writes to coexist. Unsupported ownership versions are rejected
when consulted to disambiguate a `Topic` entry.

Without ownership metadata, preserve the existing conservative compatibility rules: a metadata-marked `Topic` key
without a `Local` value is legacy; overlapping marked values are rejected before migration writes; unmarked raw
`Topic` entries remain untouched. Visible unmarked collisions still reject new canonical assignments unless
canonical ownership is already recorded. Missing ownership alone does not trigger a write during restoration.

Migration records canonical ownership before removing only the migrated legacy key. Plain helper null updates
physically delete the canonical value, sensitivity, and ownership entries. Wrapped declarative clears retain the
existing stored blank representation with its sensitivity and ownership.

Point operations use key-level `PortableValue` existence probes, including for metadata with an explicit `None`
value. Scope enumeration remains appropriate for whole-state restoration and read-only snapshots, but not for
each point operation in a growing batch. Ad hoc expression snapshots never persist migration or ownership updates.

Checkpoint stores must preserve these private entries together with workflow values. This format is
backward-readable by the new runtime; resuming mixed-scope checkpoints on older runtimes is not supported.
