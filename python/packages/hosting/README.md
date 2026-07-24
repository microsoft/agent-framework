# agent-framework-hosting

Shared execution-state helpers for app-owned Agent Framework hosting.

This package keeps Agent Framework state separate from web-framework concerns:

- `AgentState` — pairs an agent target with a core `SessionStore`
  (`session_id -> AgentSession`).
- `WorkflowState` — resolves a workflow target, including direct `Workflow`
  instances, workflow factories, `WorkflowBuilder`, and orchestration builders.

The experimental `SessionStore` and `FileSessionStore` implementations live in
`agent-framework-core` and are imported from `agent_framework`. `SessionStore`
provides `get`/`set`/`delete` by an app-selected id. Each
successful `get` returns an independent copy, so a run works from a snapshot
instead of mutating an older continuation point in place. The store does not
know how to create a new value for an id it hasn't seen before — use
`AgentState.get_or_create_session(...)` for that, since only the state object
has both the store and the resolved target. Workflow
checkpointing should use the existing `CheckpointStorage` abstraction directly;
if an app needs per-session resume, keep a small app-owned cursor such as
`session_id -> checkpoint_id`.

Session-store IDs are limited to 128 characters containing ASCII letters,
digits, `-`, and `_`. This keeps protocol-derived IDs safe to pass through
common storage backends, but it does not replace parameterized queries or
backend-specific validation in custom stores.

`FileSessionStore` uses msgspec JSON. Custom objects placed in
`AgentSession.state` must be registered explicitly before the session is saved
or restored:

```python
from agent_framework import register_state_type


class MyState:
    ...


# Register at module import time, before any provider instance is created.
register_state_type(MyState, type_id="my_state")
```

Classes with `to_dict()` / `from_dict()` methods and explicitly registered
Pydantic models receive default codecs. Other classes can provide `encoder=`
and `decoder=` callbacks. Keep registration at module level so importing the
module prepares cold-start session restoration before its context provider is
instantiated.

JSON is the default file format. Use MessagePack for a compact binary file:

```python
store = FileSessionStore("storage/sessions", serialization_format="msgpack")
```

Use FastAPI, Starlette, Azure Functions, Django, or another framework for route
registration, auth, middleware, response construction, and background work.

> The core `SessionStore` is an in-memory `dict` with no eviction — every
> id ever stored stays resolvable for the life of the process. That is
> intentional: protocols such as OpenAI Responses'
> `previous_response_id` are designed to let a caller continue from *any*
> earlier point in a conversation, not just the latest turn, so every id
> handed out needs to stay independently resolvable. If you back the store
> with real storage (Redis, a database, ...), you are responsible for that
> store's own TTL/eviction policy; this in-memory reference implementation
> does not model that concern.

## Quickstart

```python
from agent_framework import FileSessionStore
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentState

agent = OpenAIChatClient().as_agent(name="Assistant")
state = AgentState(agent, session_store=FileSessionStore("storage/sessions"))
session = await state.get_or_create_session("conversation-1")
result = await (await state.get_target()).run("Hello", session=session)
```

If a protocol mints a new continuation id on every response, store the session
explicitly after `run(...)` returns. `run(...)` may update the session, so store
the post-run object:

```python
session = await state.get_or_create_session(previous_response_id)
result = await (await state.get_target()).run("Hello", session=session)
await state.set_session(response_id, session)
```

This response-keyed pattern supports simultaneous branches: callers may read
the same `previous_response_id`, receive independent working copies, and store
each result under a different new response id. A stable `conversation_id` is
different: explicitly write the completed session back under that same id to
advance its mutable head, and ensure only one caller advances it at a time.
`AgentState` does not provide that application-level locking or optimistic
concurrency control.

Targets can be direct instances, synchronous factories, asynchronous factories,
or awaitables:

```python
state = AgentState(create_agent)  # cached by default
state = AgentState(create_agent, cache_target=False)
```

`WorkflowState` mirrors this shape for workflow targets:

```python
from agent_framework import InMemoryCheckpointStorage
from agent_framework_hosting import WorkflowState

state = WorkflowState(create_workflow)
storage = InMemoryCheckpointStorage()
result = await (await state.get_target()).run("Hello", checkpoint_storage=storage)
latest = await storage.get_latest(workflow_name=(await state.get_target()).name)
```

A `Workflow` instance allows only one active run. Hosts that need simultaneous
workflow runs should pass a factory or builder and set `cache_target=False` so
each request receives a fresh workflow instance.

`WorkflowState` also accepts an unbuilt workflow builder directly:

```python
from agent_framework import WorkflowBuilder
from agent_framework_hosting import WorkflowState

builder = WorkflowBuilder(start_executor=executor)
state = WorkflowState(builder)  # calls builder.build() when the target is resolved
```

This is structural: orchestration builders from `agent_framework_orchestrations`
(`SequentialBuilder`, `ConcurrentBuilder`, `HandoffBuilder`, `GroupChatBuilder`,
and `MagenticBuilder`) also work because they expose the same zero-argument
`build() -> Workflow` method.

Cross-channel identity linking, multicast delivery, background runs,
continuation tokens, and durable delivery runners are follow-up enhancements,
not part of this v1 state surface.
