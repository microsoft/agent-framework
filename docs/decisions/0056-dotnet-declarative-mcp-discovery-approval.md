---
status: proposed
contact: baywet
date: 2026-11-10
deciders: [baywet, westey-m]
informed: [rhurey]
---

# Separate MCP discovery consent from tool invocation approval

## Context and Problem Statement

An approval-gated declarative MCP action needs the current tool definition before
it can bind an invocation approval to that definition. Obtaining the definition
is itself a network operation using the configured endpoint and transport
settings. Approval to invoke a tool and permission to contact its server are
different decisions.

The executor cannot determine whether discovery will carry credentials merely by
checking workflow headers: managed connections, custom handlers, and configured
HTTP clients may also supply them. Workflow expressions can change while an
approval is pending, and headers must not become durable checkpoint state.

## Decision Drivers

- Obtain consent before contacting a server for an approval-gated action.
- Bind each consent to its captured destination, workflow headers, and connection reference.
- Require invocation approval after discovering the current published definition.
- Preserve request isolation, replay handling, and credential nonpersistence.
- Support custom handlers and all supported .NET targets.

## Considered Options

- Discover with configured transport settings before requesting tool approval.
  Good: one approval interaction and discovery works with authenticated servers.
  Neutral: metadata discovery remains a separate handler invocation.
  Bad: discovery contacts the destination before any consent.
- Discover without workflow headers before requesting tool approval.
  Good: explicit workflow headers are not sent during discovery.
  Neutral: the executor still performs a network operation before consent.
  Bad: authenticated discovery can fail, and other credential sources remain.
- Obtain discovery consent, then obtain a definition-bound invocation approval.
  Good: no handler invocation occurs before discovery consent, including when
  authentication is supplied outside workflow headers.
  Neutral: discovery and invocation remain separate, invocation-owned MCP calls.
  Bad: approval-gated tool calls require two interactions rather than one.

## Decision Outcome

Chosen option: "Obtain discovery consent, then obtain a definition-bound invocation
approval", because it does not depend on the executor detecting every possible
credential source.

For approval-gated actions, the initial request authorizes `tools/list` against
the displayed destination using the configured transport settings. The destination,
workflow headers, and connection reference are captured; host-managed transport
credentials remain subject to the handler's lifecycle. Discovery consent does not
authorize the requested tool invocation. After consent, discovery produces a
separate approval for the captured tool name and arguments. That approval includes
a fingerprint of the complete published tool definition in its internal snapshot.
Before invocation, the executor discovers the definition again and requests fresh
invocation approval if it differs or the previous snapshot lacks a fingerprint.
Changed metadata does not authorize an invocation.

The reserved `tools/list` action is discovery itself: its single approval
authorizes that operation, without requiring it to appear in the tool catalog.
Actions without approval retain their existing direct-invocation behavior.

Each stage uses a distinct request identifier. Responses use captured invocation
parameters rather than reevaluating them. Headers remain in memory only. Approval
snapshots include a keyed fingerprint of captured workflow headers, but neither
the header values nor the key are persisted. Hosts can provide a stable,
cryptographically random key of at least 32 bytes to support cross-process
restoration. When omitted, a process-local key is used; a checkpoint cannot be
resumed after that key is lost. After restoration, changed headers require fresh
discovery consent, while a missing or changed fingerprint key fails closed until
the original key is restored. Older snapshots without a header fingerprint
restart discovery approval. Denied or consumed requests cannot authorize a later
stage.

Handlers must return structured `tools/list` output containing complete protocol
tool definitions, including annotations and metadata. Object properties are
compared in ordinally sorted order recursively; array order and scalar values are
preserved. Missing or ambiguous definitions stop the action rather than bypassing
approval. This compares published metadata, not server implementation identity,
and does not eliminate the interval between discovery and invocation.

Existing approval UIs must handle the additional discovery request and its
notice. When an `ExternalInputRequest` is delivered through `WorkflowSession`,
informational text accompanying its inner approval content is preserved in
delivery order. Older snapshots without discovery consent restart discovery
approval. The ADR remains proposed pending the listed deciders' PR review.
