# agent-framework-hosting

Shared execution-state helpers for app-owned Agent Framework hosting.

This package keeps Agent Framework state separate from web-framework concerns:

- `AgentState` — pairs an agent target with a `SessionStore`
  (`session_id -> AgentSession`).
- `WorkflowState` — resolves a workflow target, including direct `Workflow`
  instances, workflow factories, `WorkflowBuilder`, and orchestration builders.

`SessionStore` is plain storage: `get`/`set`/`delete` by an app-selected id,
nothing more. It does not know how to create a new value for an id it hasn't
seen before — use `AgentState.get_or_create_session(...)` for that, since only
the state object has both the store and the resolved target. Workflow
checkpointing should use the existing `CheckpointStorage` abstraction directly;
if an app needs per-session resume, keep a small app-owned cursor such as
`session_id -> checkpoint_id`.

Use FastAPI, Starlette, Azure Functions, Django, or another framework for route
registration, auth, middleware, response construction, and background work.

> The built-in `SessionStore` is an in-memory `dict` with no eviction — every
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
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentState

agent = OpenAIChatClient().as_agent(name="Assistant")
state = AgentState(agent)

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
