# agent-framework-hosting

Shared execution-state helpers for app-owned Agent Framework hosting.

This package keeps Agent Framework state separate from web-framework concerns:

- `AgentFrameworkState` — stores an agent/workflow target and optional session
  state for routes that the app owns.
- `SessionStore` — maps an app-selected session id to an `AgentSession` for
  non-persisted servers.
- Existing experimental channel-hosting types remain available while the package
  is unreleased, but the v1 direction is protocol helpers plus app-owned routes.

Use FastAPI, Starlette, Azure Functions, Django, or another framework for route
registration, auth, middleware, response construction, and background work.

## Quickstart

```python
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentFrameworkState, SessionStore

agent = OpenAIChatClient().as_agent(name="Assistant")
state = AgentFrameworkState(agent, session_store=SessionStore)

session = await state.get_session("conversation-1")
result = await (await state.get_target()).run("Hello", session=session)
```

Targets can be direct instances, synchronous factories, asynchronous factories,
or awaitables:

```python
state = AgentFrameworkState(create_agent)  # cached by default
state = AgentFrameworkState(create_agent, cache_target=False)
```

Cross-channel identity linking, multicast delivery, background runs,
continuation tokens, and durable delivery runners are follow-up enhancements,
not part of this v1 state surface.
