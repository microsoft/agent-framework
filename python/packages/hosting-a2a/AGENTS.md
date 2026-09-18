# A2A Hosting Helpers (`agent-framework-hosting-a2a`)

Conversion and native card-generation helpers for hosting Agent Framework
agents and workflows through an application-owned A2A server.

## Public API

- `a2a_to_run(message, *, stream=False)` converts an A2A `Message` to
  `AgentRunArgs`; pass `input_modes` for optional advertised-mode validation.
- `a2a_from_run(result)` converts an Agent Framework response, message, or
  streaming update to A2A `Part` values; pass `output_modes` for optional
  advertised-mode validation.
- `await AgentA2AAdapter(target, ...).get_card()` creates a native `AgentCard`
  from an agent or `AgentState`, target metadata, and explicit A2A discovery
  policy. The adapter also re-exposes `a2a_to_run(...)` and
  `a2a_from_run(...)`, validating against configured card modes by default.
- `a2a_to_workflow_run(message, workflow)` validates one text, raw, or data
  part against the workflow's single start-executor input type.
- `a2a_from_workflow_run(result)` converts completed public workflow outputs
  to native A2A parts and rejects pending external-input requests.
- `await WorkflowA2AAdapter(target, ...).get_card()` creates a native `AgentCard`
  from a workflow or `WorkflowState` and infers defensible modes from declared
  workflow types. The adapter also re-exposes the workflow conversion helpers
  as `await a2a_to_run(...)` and `a2a_from_run(...)`, validating against
  effective card modes by default. Inferred workflow output modes are resolved
  by `get_card()` before validated output conversion.

## Boundary

This package does not provide an `AgentExecutor`, routes, a web application,
task stores, event queues, task state policy, artifact ID policy, or outbound
delivery. Applications compose the conversion helpers with native A2A SDK
constructs.

`a2a_from_run(...)` intentionally returns a flat part list. It preserves
content-level metadata, while applications own A2A message and artifact
boundaries plus message-level metadata.

Card builders return native A2A protobuf values; do not create a parallel card
model or subclass. `AgentA2AAdapter` infers built-in Agent Framework skills from
the resolved agent's `SkillsProvider` instances by default; `infer_skills=False`
disables this. The `skills` argument accepts both Agent Framework `Skill`
values and native A2A `AgentSkill` values. Do not infer A2A skills from function
tools. Capabilities such as streaming and push notifications remain explicit
because they describe the application server. Skill discovery runs with a
`SkillsSourceContext` containing the resolved agent and no session.

`supported_interfaces` contains one native `AgentInterface` per public
protocol endpoint. The URL is where the application mounted the corresponding
A2A routes, and the binding must match the protocol actually served there
(commonly `JSONRPC`, `HTTP+JSON`, or `GRPC`).

A2A mode strings are extensible, but automatic parsing is intentionally
limited to `text`, `application/json`, `application/octet-stream`, and
pass-through concrete media types (with wildcard validation such as
`image/*`). JSON-only output parses Agent Framework JSON text into native A2A
data parts; structured workflow output becomes a data part, or JSON text when
only `text` is advertised. Custom modes are accepted when a native part already
carries that media type, and otherwise raise instead of guessing a serializer.

Workflow mode inference is conservative: string schemas map to `text`, binary
strings to `application/octet-stream`, and JSON-compatible schemas to
`application/json`. Unknown application-specific representations require
explicit card modes and custom application conversion.
