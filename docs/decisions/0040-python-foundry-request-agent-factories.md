---
status: proposed
contact: RogerBarreto
date: 2026-09-10
deciders: RogerBarreto
---

# Request-scoped agent factories for Python Foundry hosting

## Context and Problem Statement

Python Foundry hosts accept an agent instance and separate persisted state by user and conversation.
Some agent implementations also hold mutable execution state outside their `AgentSession`.
A workflow's executors, pending requests, and internal conversation therefore need their own lifetime,
independent of the server object's lifetime.

## Decision Drivers

- Preserve ordinary-agent instance callers and existing protocol formats.
- Create independent workflow execution objects for each request.
- Continue authorized conversations from stored state, including after process recreation.
- Avoid a core workflow redesign or a cache of live runtimes with expiration policies.

## Considered Options

| Option | Benefit | Cost |
| --- | --- | --- |
| Factory per request | Explicit ownership; same construction path for fresh calls and recovery | Applications rebuild mutable runtime objects and manage client ownership |
| Runtime cache per user and session | Avoids rebuilding objects on every call | Requires expiration, eviction, cleanup, concurrency controls, and a separate restart path |
| Move workflow runtime into a new core session type | Separates shared definitions from session state throughout the framework | Larger change to core execution and serialization contracts |
| Continue accepting shared workflow instances | No caller migration | Persisted-state isolation does not separate live workflow state |

## Decision Outcome

Add `agent_factory` to `ResponsesHostServer` and `InvocationsHostServer`. It is a zero-argument callable
returning an agent or an awaitable agent. Resolve it within the current platform request context and
keep the result local until execution, persistence, and streaming have finished.

Retain `agent` for ordinary instances. Require factories for the two built-in workflow-agent types,
recognized by one private Foundry helper. Do not add a public workflow-recognition interface or attempt
to inspect arbitrary application wrappers.

Responses continues using its conversation/response checkpoint scopes. Invocations adds workflow
checkpoint persistence scoped to user and invocation session without changing its text protocol.
Functional workflows need their own checkpoint adaptation because saved-input replay differs from
graph workflow restoration.

Functional resilient Responses recovery is explicitly unsupported: checkpoints omit buffered output
from completed steps, so a hosting adapter cannot restore that output without rerunning application
work. Invocations retains its text-only exchange and rejects pending or interrupted functional
continuations; a new message after clean completion is supported.

The host manages an agent's exposed async context manager. It does not recursively discover resources
inside executors or closures. Applications must construct fresh mutable runtime objects and give
shared clients a lifetime that outlasts every request using them.

Serialize updates to the same workflow scope within a host process. Do not describe these locks as
distributed coordination or checkpoint replay as exactly-once execution.

## Consequences

Workflow callers migrate from `Host(workflow_agent)` to `Host(agent_factory=create_agent)`.
The factory must construct new mutable objects, not return the same instance or reuse stateful executors.
Stable workflow names, executor IDs, and serialization registrations are necessary for continuation.

Ordinary-agent instance callers keep their existing lifecycle. Factories do not automatically save
arbitrary custom agent fields, and the Invocations text protocol still does not provide a complete
external approval exchange. A core session redesign remains a separate possible improvement.
