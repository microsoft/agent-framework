# agent-framework-hosting-a2a

A2A conversion helpers for app-owned Agent Framework hosting.

The package deliberately does not choose a web framework or wrap the A2A SDK
server lifecycle. It provides two conversion functions:

- `a2a_to_run(...)` converts a native A2A `Message` into Agent Framework run
  arguments.
- `a2a_from_run(...)` converts an `AgentResponse`, `Message`, or streaming
  `AgentResponseUpdate` into native A2A `Part` values.

Application code keeps ownership of the A2A SDK's `AgentExecutor`,
`RequestContext`, `TaskUpdater`, event queue, task store, routes, task state,
artifact IDs, authentication, and deployment.

`a2a_from_run(...)` preserves content-level metadata on each returned part and
flattens completed responses in message order. The application decides how to
group those parts into A2A messages or artifacts and owns their message-level
metadata and boundaries.

```python
run = a2a_to_run(context.message)
session_id = f"a2a:{context.tenant}:{context.context_id}"
session = await state.get_or_create_session(session_id)
result = await agent.run(
    run["messages"],
    session=session,
    options=run["options"],
)
await state.set_session(session_id, session)
parts = a2a_from_run(result)

# Native A2A SDK application code publishes `parts` with TaskUpdater.
```

The surrounding A2A application may use Starlette, FastAPI, another ASGI
framework, or the SDK's own application builders. These helpers do not care.
