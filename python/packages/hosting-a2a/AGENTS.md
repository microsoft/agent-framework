# A2A Hosting Helpers (`agent-framework-hosting-a2a`)

Side-effect-free conversion helpers for hosting Agent Framework agents through
the native A2A SDK.

## Public API

- `a2a_to_run(message, *, stream=False)` converts an A2A `Message` to
  `AgentRunArgs`.
- `a2a_from_run(result)` converts an Agent Framework response, message, or
  streaming update to A2A `Part` values.

## Boundary

This package does not provide an `AgentExecutor`, routes, a web application,
task stores, event queues, task state policy, artifact ID policy, or outbound
delivery. Applications compose the conversion helpers with native A2A SDK
constructs.

`a2a_from_run(...)` intentionally returns a flat part list. It preserves
content-level metadata, while applications own A2A message and artifact
boundaries plus message-level metadata.
