---
status: accepted
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
a conversation, session, or thread; chat clients happen to map it through the abstract `conversation_id` ChatOption, but
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

### Concrete gap example

At the protocol level, the durable continuation payload shapes are different:

```json
// A2A: future calls may need multiple durable protocol fields
{
  "context_id": "ctx_123",
  "task_id": "task_789",
  "task_state": "input_required"
}
```

```json
// OpenAI Responses: future calls usually need one continuation value
{
  "previous_response_id": "resp_abc123"
}
```

The gap is that A2A continuation state is multi-field while OpenAI continuation is
typically single-field.

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
- Option B: Extend `service_session_id` with richer service-owned values.
- Option C: Add a dedicated dict for additional session details.
- Option D: Store additional durable state inside `AgentSession.state`.

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

### Option B: Extend `service_session_id` with richer service-owned values

Keep the common `service_session_id` case as a plain string. When an agent/service needs more than one service-owned
continuation value, allow `service_session_id` to be a typed structured value, such as a `TypedDict`. The main session ID
used for `gen_ai.conversation.id` should still be extracted by the owning agent, not inferred by generic telemetry code.

Examples:

```python
simple_session = AgentSession(
    service_session_id="resp_123",
)

structured_session = AgentSession(
    service_session_id=A2AServiceSessionId(
        context_id="ctx_123",
        task_id="task_789",
        task_state=TaskState.TASK_STATE_WORKING,
    ),
)
```

- Good, because the common case remains a plain string and stays simple.
- Good, because richer service-owned continuation state stays under the existing continuation property.
- Good, because a structured value can make framework-side validation possible before a value is sent back to a service.
- Good, because A2A can keep `context_id`, `task_id`, and `task_state` together as the service/protocol-owned continuation
  value without adding A2A fields to base `AgentSession`.
- Neutral, because telemetry needs an agent-owned extractor to pick the `gen_ai.conversation.id` value from either a
  string or structured `service_session_id`.
- Neutral, because Python A2A would need a pre-release adjustment to stop relying on `A2AAgentSession` for these fields.
- Bad, because changing the `service_session_id` type is a compatibility risk for users, providers, serialization, and
  tests.
- Bad, because every path that sends `service_session_id` back to a service must consistently extract/adapt the
  service-owned continuation component.

### Option C: Add a dedicated dict for additional session details

Keep `service_session_id` as the primary opaque service-owned continuation handle, and add a separate dictionary for
additional durable protocol/service values that need to travel with the session.

Example:

```python
session = AgentSession(
    service_session_id="ctx_123",
    session_details={
        "task_id": "task_456",
        "task_state": TaskState.TASK_STATE_WORKING,
    },
)
```

- Good, because the main service continuation handle stays a plain `service_session_id` string.
- Good, because extra state has an explicit home and does not overload `service_session_id`.
- Good, because generic consumers can look in one documented place for additional session-scoped values.
- Neutral, because helper APIs can hide the raw dictionary access.
- Bad, because this still introduces string-keyed state unless the dict values are wrapped by typed helpers.
- Bad, because it adds another public session field that needs serialization, naming, and compatibility rules.
- Bad, because generic consumers still need to understand the shape or use helpers for the selected agent/session type.

### Option D: Store additional durable state inside `AgentSession.state`

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

## Decision

Chosen decision criteria for the future: **split identity by lifecycle**.

When a protocol emits an id/token, place it by answering "what lifecycle does this value serve?":

- **Future-call continuation state** -> durable session state. Examples: A2A `context_id` + `task_id` + `task_state`;
  OpenAI Responses `previous_response_id`/`conversation`.
- **Single-result identity** -> response/message object only. Examples: OpenAI `resp_*`, A2A `message_id`,
  A2A `artifact_id`.
- **Resume unfinished work** -> `ContinuationToken` only. Example: a token carrying in-progress task resume data.
- **Run-start-only request fields** -> run method arguments/options, not durable session state. Example: A2A
  `reference_task_ids` for a specific follow-up/refinement request.
- **Per-run correlation/telemetry** -> protocol wrapper or run context, not `AgentSession`. Example: wrapper-managed
  `run_id` used only for tracing/events.

Durable-state option decision: **Option B: Extend `service_session_id` with richer service-owned values**.
This does **not** add a new top-level identity abstraction; it keeps continuation identity under
`service_session_id` and keeps run correlation in existing run/telemetry context.
The immediate implementation gap is mainly in A2A mapping clarity, but the lifecycle split applies
consistently across providers.

To support telemetry, `BaseAgent` should expose a method that accepts an `AgentSession | None` and returns the value to
use for `gen_ai.conversation.id`. The default implementation should return `session.service_session_id` when it is a
string. Agents that use a structured `service_session_id`, such as `A2AAgent`, should override that method and return the
appropriate primary session/context value.

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

## Appendix: implementation notes for Option B

The exact names are implementation details, but the shape should be:

```python
class A2AServiceSessionId(TypedDict):
    context_id: str
    task_id: str | None
    task_state: TaskState | None


class AgentSession:
    def __init__(
        self,
        *,
        session_id: str | None = None,
        service_session_id: str | ServiceSessionId | None = None,
    ) -> None:
        ...


class BaseAgent:
    def _get_otel_conversation_id(self, session: AgentSession | None) -> str | None:
        service_session_id = session.service_session_id if session else None
        return service_session_id if isinstance(service_session_id, str) else None


class A2AAgent(BaseAgent):
    def _get_otel_conversation_id(self, session: AgentSession | None) -> str | None:
        service_session_id = session.service_session_id if session else None
        if isinstance(service_session_id, Mapping):
            return service_session_id.get("context_id")
        return service_session_id if isinstance(service_session_id, str) else None


class AgentTelemetryLayer:
    def _trace_agent_invocation(...):
        attributes = _get_span_attributes(
            ...,
            thread_id=self._get_otel_conversation_id(session),
            ...,
        )
```

This keeps the OpenTelemetry extraction decision with the agent that owns the service continuation shape. Generic OTel
code should not parse structured `service_session_id` values directly.

`AgentSession` must also be updated so `service_session_id` can store either the current string value or a structured
service-owned value. Serialization must preserve both shapes, and existing serialized sessions with string
`service_session_id` must continue to round-trip unchanged.

## More Information

Related work and issues:

- #4673: native conversation ID propagation.
- #4893: align A2A protocol concepts with Agent Framework session/continuation concepts.
- #2931: Foundry-specific conversation creation helper, split into a separate Python PR.
- #6622: broader provider-agnostic conversation creation API discussion requiring .NET sync.
- [ADR-0015](0015-agent-run-context.md): AgentRunContext for Agent Run.
- [ADR-0018](0018-agentthread-serialization.md): AgentSession serialization.
- [ADR-0026](0026-hosted-session-identity-context.md): hosted session identity context.
