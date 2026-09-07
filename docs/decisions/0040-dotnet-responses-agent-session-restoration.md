---
status: proposed
contact: rogerbarreto
date: 2026-09-07
deciders: [rogerbarreto]
---

# .NET Responses: opt-in agent session restoration

## Context and Problem Statement

DevUI approval responses require both conversion of `function_approval_response` and restoration of the session that holds the pending approval. The route-owning Responses executors currently replay conversation messages but do not use the `AgentSessionStore` configured by `WithSessionStore` or `WithInMemorySessionStore`. Message replay cannot restore workflow checkpoints.

This decision supersedes only the unchanged-`MapOpenAIResponses`-behavior constraint in [ADR-0032](0032-dotnet-hosting-protocol-helpers.md) for hosts that explicitly configure a session store. The side-effect-free protocol helpers and the default behavior without a session store remain unchanged.

## Considered Options

1. Automatically create an in-memory session store for every endpoint. Simple to enable, but changes default retention and execution behavior without the host opting in.
2. Require applications to replace the Responses routes or write session middleware. Preserves the current executors, but leaves the existing session-store registration ineffective for DevUI.
3. Resolve the explicitly registered store in the Responses executor and restore the agent session before invocation. Reuses existing hosting abstractions without introducing another public state holder.

## Decision Outcome

Choose option 3:

- `ResolveSessionStore` uses the resolved agent's name for keyed lookup, then the non-keyed default store. A request cannot select another store for an endpoint already bound to an agent. No registration means no session persistence.
- Existing isolation wrappers are preserved. Raw stores are scoped using a registered `AgentIsolationKeyProvider`; missing identity fails when a provider requires it.
- `HostedAgentSessionKey.Resolve` encapsulates the lookup rule: the conversation head, a previous response snapshot, or the newly generated response ID. IDs remain opaque; Foundry-specific response-ID partition extraction is not applicable.
- The agent creates and deserializes its own session through the store. A session-backed run does not replay the conversation transcript, which would duplicate history and processed approvals.
- Successful runs save a response snapshot unless `store` is `false`, and advance the conversation head when specified. Completion is not published until persistence finishes. Execution or persistence failures and cancellation propagate without publishing successful completion.
- Deleting a response also deletes its session snapshot. The conversation head remains independent of response snapshots.
- Workflow streaming emits the approval from `RequestInfoEvent`, which carries the workflow-facing request ID, rather than also emitting the inner agent's approval.

## Consequences

Hosts can resume approvals and workflow checkpoints using the existing explicit registration. Previous-response continuations remain independent branches, while conversation IDs identify mutable heads.

Hosts remain responsible for endpoint authorization, session-store retention, stable agent identities, and coordination of simultaneous turns targeting the same conversation. The store and conversation transcript are separate: transcript edits do not rewrite agent state. In-memory session stores do not provide restart durability, and their retention is independent of the Responses cache.
