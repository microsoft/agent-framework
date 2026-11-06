---
status: proposed
date: 2026-09-21
deciders: eavanvalkenburg, westey-m
---

# Preserve host runtime context through MCP invocation and approval

## Context and Problem Statement

Workflow client kwargs, tool runtime kwargs, model arguments, and reviewed transport headers have different
destinations and lifetimes. Flattening them loses provenance; retaining only an operation across a delayed approval
does not preserve the transport context under which that operation was reviewed.

## Considered Options

- Reverse precedence in the shared argument mapping. This protects collisions but changes tool arguments and still
  permits model-only values to supply authentication inputs.
- Persist evaluated headers or an unkeyed digest with the approval. This supports restart-transparent comparison but
  exposes credentials or permits offline guessing of low-entropy header values.
- Use executor-local ephemeral binding keys. This keeps keys out of storage, but can cause endless reapproval when
  each resume reconstructs the executor on a different worker.
- Separate host runtime inputs and retain keyed approval verification in trusted workflow checkpoint state.
  This keeps credentials out of checkpoints and keys out of approval payloads, but requires protected host storage.

## Decision Outcome

Choose separate host inputs and workflow-local keyed bindings:

- Declarative agent execution resolves both kwargs buckets per executor, including legacy checkpoint state, and
  forwards them through their matching Agent parameters. It does not copy the outer bag into tool inputs.
- Generated MCP functions preserve host runtime kwargs in an owner-scoped context separate from merged tool
  arguments. HTTP header providers read only host context. The scope is reset on success, error, and cancellation.
  Direct host calls keep their existing kwargs-based API; model precedence remains unchanged for tool arguments.
- Declarative MCP approvals contain header names and an HMAC over the request ID and canonical evaluated headers.
  The random binding key is retained separately in trusted host checkpoint state, never in approval payloads.
  Header names compare case-insensitively, values exactly; no raw credentials or unkeyed digests enter checkpoints.
- A changed or unverifiable header set produces a fresh approval for the pinned operation before dispatch. This
  includes legacy requests, credential rotation, and missing verification state. Unchanged approvals remain valid
  across executor reconstruction using the checkpointed key. Headerless requests retain their resume behavior.

These are intentional compatibility changes: applications deriving generated-call headers from model arguments must
move trusted values into host runtime context or a provider closure. Consumers of delayed approvals must handle
replacement request IDs. Checkpoints already hold approval authority and must be protected against unauthorized reads
and writes; the binding key inherits that host trust boundary. Custom handlers and client providers remain responsible for
principal changes in credentials resolved outside the action's evaluated headers.

The proposed deciders are Python code owners; maintainer and engineering-management approval is still required.
