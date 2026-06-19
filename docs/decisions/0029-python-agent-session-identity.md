---
status: proposed
contact: eavanvalkenburg
date: 2026-06-19
deciders: eavanvalkenburg, moonbox3, TaoChenOSU, chetantoshnival
consulted: westey-m
informed:
---

# Python identity lifetimes for sessions, tasks, and continuation

## Context and Problem Statement

Python `AgentSession` currently carries a local `session_id`, an optional opaque service continuation
`service_session_id`, and provider state. `service_session_id` is any service-owned value that lets that service continue
a conversation, session, or thread; chat clients happen to map it through the abstract `conversation_id` option, but
other agent types can use it differently. It is not a generic correlation field, and generic correlation should not
require parsing or understanding that opaque service-owned value.

The related issues mix values with different lifetimes:

- **Session / conversation identity**: values that group a multi-turn interaction. Examples: A2A `context_id`, OpenAI
  Responses `conversation` (`conv_*`) or response-chain continuation (`previous_response_id`).
- **Task identity**: values that identify a protocol task and may affect future protocol calls. Example: A2A `task_id`.
- **Message / response identity**: values that identify an output message or response. Examples: A2A `message_id` /
  `artifact_id`, OpenAI Responses response id (`resp_*`).
- **Continuation token**: a framework resume payload for in-progress work. It may contain the same underlying value as a
  protocol id, such as A2A `task_id`, but it only exists when there is an unfinished operation to resume.

These values should not automatically live in the same object just because they all help "continue" something. A value
belongs in `AgentSession` only when it is needed to continue future calls across turns. A value that identifies one
result belongs on the response or message. A value that resumes in-progress work belongs in a `ContinuationToken`.

An `AgentSession` created for one agent is not expected to be guaranteed to work against another agent. When a session is
used with an incompatible agent, protocol, or service, the framework should still help users understand what is wrong as
early as possible, preferably before calling out to the remote service.

For #4673, native conversation identity propagation should be based on `AgentSession` where the value is durable session
state. For #4893, A2A `context_id` and `task_id` need a coherent Agent Framework mapping.

AG-UI is out of scope for the decision. Its `thread_id` already maps to `AgentSession.session_id` in the normal wrapper
path, and `run_id` is wrapper-owned event correlation. If AG-UI run correlation needs framework telemetry integration
later, that should be handled as a run-context/telemetry design, not as session identity.

## Current implementation notes

- A2A currently has `A2AAgentSession`, but `A2AAgent.create_session(...)` does not automatically return it.
- A2A currently mirrors `context_id` into `service_session_id`; that is current behavior, not necessarily the target
  abstraction.
- A2A `task_id` is not just cosmetic correlation. It is used for `task_id` when a task is `INPUT_REQUIRED`, for
  `reference_task_ids` when refining a previous task, and inside `A2AContinuationToken` for in-progress tasks.
- `RawAgent._prepare_run_context(...)` currently forwards `active_session.service_session_id` as chat `conversation_id`,
  so any non-string or formatted value affects existing chat-client paths.
- `OpenAIChatClient` maps chat options `conversation_id` to the Responses API as `previous_response_id` for `resp_*`,
  `conversation` for `conv_*`, and defaults unrecognized strings to `previous_response_id`. When `store` is not `False`,
  it returns `response.conversation.id` when available, otherwise `response.id`, as the next service continuation value.
- For Responses API, the response id (`resp_*`) is also the response/message identity surfaced as
  `ChatResponse.response_id`; when used for continuation on the next request, it becomes the `previous_response_id`
  value.
- Python A2A has not been released as stable yet, so its session factory or session shape can still be adjusted before
  release.

## Decision Drivers

- Preserve `AgentSession.session_id` as the local/client conversation identity.
- Preserve `AgentSession.service_session_id` as an opaque service-owned continuation handle.
- Keep `AgentSession` for durable state needed across turns, not per-run bookkeeping.
- Store values needed by future calls in durable session state; keep values that only resume in-progress work in
  `ContinuationToken`.
- Fix the current confusion where session, task, response, and continuation values can be treated as interchangeable
  because they all participate in "continuing" something.
- Make the implementation following this ADR preserve the lifetime split clearly: future-call state, in-progress resume
  tokens, response/message ids, and protocol event correlation must not be silently mixed.
- Expose durable continuation state in a typed way when future calls depend on it.
- Let telemetry correlate runs without parsing opaque service continuation handles.
- Reuse existing run/context surfaces before introducing a new identity abstraction.
- Keep MCP and other remote tool boundaries safe: framework identity must not be forwarded to remote tools unless an
  existing explicit opt-in mechanism says so.
- Keep existing `AgentSession.to_dict()` / `from_dict()` migration and compatibility straightforward.
- Stay close to .NET where there is already behavior to match, especially A2A's `ContextId`, `TaskId`, and `TaskState`.
- Detect incompatible session identity shapes as early as practical, preferably before a remote service call.

## Non-goals

- Do not design a provider-agnostic conversation creation API here. That is tracked separately in #6622.
- Do not make `service_session_id` a generic telemetry or run-correlation field.
- Do not introduce a new identity object if existing run/context objects can carry the selected per-run correlation value.
- Do not make a session from one agent guaranteed to work against another agent.
- Do not optimize the public `agent.run(...)` API for protocol-wrapper internals.

## Remaining question: durable shape for additional continuation state

- Option A: Use protocol-specific `AgentSession` subclasses.
- Option B: Store additional durable state inside `AgentSession.state`.
- Option C: Extend `service_session_id` with richer service-owned values.

### Option A: Use protocol-specific `AgentSession` subclasses

Each protocol or agent type that needs additional durable state keeps a specialized `AgentSession` subclass. For A2A,
that means keeping `A2AAgentSession` for A2A-specific durable state and changing `A2AAgent.create_session(...)` to return
that type.

Example:

```python
# First call returns a task that future A2A messages may need to reference.
session = await a2a_agent.create_session()

response = await a2a_agent.run(
    message,
    session=session,
)

# A2AAgent updates durable A2A protocol state from the returned task/status payload.
# The user does not set these manually.
assert isinstance(session, A2AAgentSession)
assert session.task_id is not None
assert session.task_state is not None

# Later call reuses the durable A2A session state. A2AAgent decides whether to send task_id
# for INPUT_REQUIRED or reference_task_ids for task refinement.
next_response = await a2a_agent.run(
    next_message,
    session=session,
)
```

- Good, because protocol-specific state stays in a protocol-specific type.
- Good, because it aligns with .NET A2A's `A2AAgentSession` shape.
- Good, because Python A2A can still make this pre-release session factory adjustment.
- Good, because `task_state` does not get promoted to a base `AgentSession` concept.
- Bad, because generic consumers cannot read protocol-specific state without knowing about the subclass or a helper API.
- Bad, because it depends on each subclass consistently setting shared session fields such as `service_session_id` where
  those are part of the shared abstraction.

### Option B: Store additional durable state inside `AgentSession.state`

Keep base `AgentSession` unchanged and store additional durable continuation/protocol state under namespaced keys in
`session.state`.

Example:

```python
session = AgentSession(session_id="ctx_123")

session.state["a2a"] = {
    "task_id": "task_456",
    "task_state": TaskState.TASK_STATE_WORKING,
}
```

- Good, because it avoids new public fields and avoids a subclass requirement.
- Good, because `AgentSession.state` already exists for provider/session state.
- Neutral, because helper APIs can hide the raw dictionary access.
- Bad, because stringly typed state is easier to corrupt and harder to validate.
- Bad, because generic consumers need helper APIs anyway; directly reading nested dictionaries is not a good abstraction.
- Bad, because users may accidentally overwrite or persist invalid protocol state.

### Option C: Extend `service_session_id` with richer service-owned values

Some services may need `service_session_id` to carry richer service-owned continuation values. That can be addressed with
a structured value or service-owned formatted string while keeping the common case as a plain string. This option remains
about service-owned continuation only; it is not the mechanism for generic run/task correlation.

Examples:

```python
simple_session = AgentSession(
    service_session_id="resp_123",
)

structured_session = AgentSession(
    service_session_id=ServiceSessionIdentity(
        continuation_id="ctx_123",
        task_id="task_789",
        task_state=TaskState.TASK_STATE_WORKING,
    ),
)
```

- Good, because the common case remains a plain string and stays simple.
- Good, because richer service-owned continuation state stays under the existing continuation property.
- Good, because a structured value can make framework-side validation possible before a value is sent back to a service.
- Neutral, because service-specific formats or structured values could be hidden behind helpers.
- Neutral, because Python A2A would likely need a pre-release adjustment to reshape or wrap `A2AAgentSession`.
- Bad, because changing the field type is a broad compatibility risk for users, providers, serialization, and tests.
- Bad, because existing chat-client code treats `service_session_id` as the opaque value to pass through the
  `conversation_id` option, so every such path must consistently extract/adapt the service-owned continuation component.
- Bad, because this does not solve generic run/task correlation unless the structured fields become framework-owned,
  which is not the purpose of `service_session_id`.

## Decision

Chosen direction: **split identity by lifecycle**.

Values that are needed by future calls must be durable session state. Values that only identify one response stay on the
response/message. Values that resume unfinished work stay in `ContinuationToken`. Values that only correlate a protocol
run should stay in the protocol wrapper or run/telemetry context, not in `AgentSession`.

Durable-state option decision: **TBD**.

## Appendix: A2A `task_id` and `reference_task_ids` implementation check

The A2A protocol distinguishes a message's `task_id` from `reference_task_ids`:

- `task_id` associates the message with a specific task.
- `reference_task_ids` provides additional task context, for example when a new task refines or follows up on the result
  of a previous task.

The protocol does not appear to prescribe that `task_id` and `reference_task_ids` are mutually exclusive. If both are
present, the natural reading is that the message is associated with one task while also referencing other tasks for
context. The serving agent decides how to interpret that context.

The Python implementation should check and likely adjust the current behavior:

- `task_id` should be updated by the current run when the remote A2A service returns a task/status payload.
- `task_id` should remain durable A2A session state when needed for future calls, for example when a task is
  `INPUT_REQUIRED`.
- `reference_task_ids` should be a run parameter / caller intent for the current request, not implicit durable session
  continuation state.
- A follow-up/refinement request should pass explicit `reference_task_ids` when it wants to reference previous tasks.
- If both session `task_id` and run `reference_task_ids` are present, the wrapper should preserve the protocol
  distinction rather than treating one as a replacement for the other.
- If no `reference_task_ids` are supplied, the wrapper should not automatically infer them from the last session task
  unless we deliberately keep that convenience for compatibility.

## More Information

Related work and issues:

- #4673: native conversation ID propagation.
- #4893: align A2A protocol concepts with Agent Framework session/continuation concepts.
- #2931: Foundry-specific conversation creation helper, split into a separate Python PR.
- #6622: broader provider-agnostic conversation creation API discussion requiring .NET sync.
- [ADR-0015](0015-agent-run-context.md): AgentRunContext for Agent Run.
- [ADR-0018](0018-agentthread-serialization.md): AgentSession serialization.
- [ADR-0026](0026-hosted-session-identity-context.md): hosted session identity context.
