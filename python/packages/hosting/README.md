# agent-framework-hosting

Shared execution-state helpers for app-owned Agent Framework hosting.

This package keeps Agent Framework state separate from web-framework concerns:

- `AgentFrameworkState` — stores an agent/workflow target and optional session
  state for routes that the app owns.
- `SessionStore` — maps an app-selected session id to an `AgentSession` for
  non-persisted servers. `get(session_id, alias=...)` resolves (creating if
  needed) and, in the same call, can register an *additional* id for the same
  session — useful when a protocol's continuation id rotates every turn (for
  example, OpenAI Responses' `previous_response_id`, which by design lets a
  caller continue from any earlier point, not just the latest turn) and a
  later request needs to resolve the new id back to the same conversation.
  `reset` forgets a session by its own id.
- Existing experimental channel-hosting types remain available while the package
  is unreleased, but the v1 direction is protocol helpers plus app-owned routes.

Use FastAPI, Starlette, Azure Functions, Django, or another framework for route
registration, auth, middleware, response construction, and background work.

> The built-in `SessionStore` is an in-memory `dict` with no eviction — every
> id it has ever seen (including aliases) stays resolvable for the life of the
> process, which is intentional for the reasons above. If you back a
> `SessionStore`-shaped store with real storage (Redis, a database, ...), you
> are responsible for that store's own TTL/eviction policy; this reference
> implementation does not model that concern.

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
