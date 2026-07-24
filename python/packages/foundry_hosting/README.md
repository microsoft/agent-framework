# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

`ResponsesHostServer` persists the Agent Framework `AgentSession` used by regular
agents in addition to the Responses provider's message history. By default it
uses core's experimental msgspec-backed `FileSessionStore` under `$HOME/.checkpoints/sessions`
when hosted and `{cwd}/.checkpoints/sessions` locally. The store is partitioned
by stable agent name, the platform user key, and the Responses conversation
partition. Foundry hashes that composite scope into a restricted-alphabet
`foundry_<hex>` session ID before it reaches the store. Pass `session_store=` to
use another `SessionStore` implementation.

Workflow agents continue to use checkpoint storage; their checkpoints share the
same `$HOME/.checkpoints` or local `.checkpoints` root.

## Custom authenticated session isolation

`ResponsesHostServer` accepts an explicit sync or async
`session_isolation_key_resolver(request, context)` callable. The default uses
Foundry's trusted `context.platform_context.user_id_key`. Hosted requests fail
closed when no key is resolved; local requests may remain unscoped.

File-backed state is partitioned under the validated identity:

```text
.checkpoints/
  sessions/user-<identity>/<conversation-id>.json
  checkpoints/user-<identity>/<context-id>/
  function-approvals/user-<identity>/approval_requests.json
```

The default store is `IsolationKeyScopedFileSessionStore`, a
`FileSessionStore` subclass. One store instance serves the server; each
`get`/`set`/`delete` operation resolves its path beneath the isolation directory
bound for that request. The server does not keep a store instance per user.
If `session_store=` is supplied with file-backed storage, it must already be an
`IsolationKeyScopedFileSessionStore`; an unscoped `FileSessionStore` is rejected.

The resolver must return a stable, globally unique, portable path-safe identity.
The value is visible in the directory name, so return an application-owned
opaque ID rather than a sensitive claim when necessary.

Python has no universal DI container or `IHttpContextAccessor`. Applications
that authenticate through ASGI middleware can explicitly bridge their verified
principal to the resolver with an application-owned `ContextVar`:

```python
from contextvars import ContextVar
from typing import Any

from agent_framework_foundry_hosting import ResponsesHostServer


current_subject: ContextVar[str | None] = ContextVar("current_subject", default=None)


class VerifiedSubjectMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # An outer authentication middleware must populate this trusted user.
        user = scope.get("user")
        subject = getattr(user, "identity", None) if getattr(user, "is_authenticated", False) else None
        token = current_subject.set(subject)
        try:
            await self.app(scope, receive, send)
        finally:
            current_subject.reset(token)


def claims_isolation_key(request: Any, context: Any) -> str | None:
    del request, context
    return current_subject.get()


server = ResponsesHostServer(
    agent,
    session_isolation_key_resolver=claims_isolation_key,
)
app = VerifiedSubjectMiddleware(server)
```

Authentication middleware must run before `VerifiedSubjectMiddleware`. Do not
use an unverified caller-controlled header as the isolation key.
