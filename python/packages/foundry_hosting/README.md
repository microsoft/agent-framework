# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

`ResponsesHostServer` persists the Agent Framework `AgentSession` used by regular
agents in addition to the Responses provider's message history. By default it
uses the experimental `FoundrySessionStore` under `$HOME/.checkpoints/sessions`
when hosted and `{cwd}/.checkpoints/sessions` locally. The store is partitioned
by the Agent Server request context's platform user key and the Responses
conversation partition. Pass `session_store=` to use another `SessionStore`
implementation.

Workflow agents continue to use checkpoint storage; their checkpoints share the
same `$HOME/.checkpoints` or local `.checkpoints` root.

## Foundry session isolation

`FoundrySessionStore` currently subclasses core's `FileSessionStore`. It reads
the active request through `azure.ai.agentserver.core.get_request_context()` and
hashes the platform `user_id` (the same `x-agent-user-id` value exposed as
`ResponseContext.platform_context.user_id_key`) before selecting an on-disk
directory. This makes the user partition path-safe and avoids persisting the raw
platform identity.

File-backed state is partitioned under the validated identity:

```text
.checkpoints/
  sessions/user-<fingerprint>/<conversation-id>.json
  checkpoints/user-<fingerprint>/<context-id>/
  function-approvals/user-<fingerprint>/approval_requests.json
```

Hosted requests require container protocol `2.0.0`. The v2-only request
`call_id` is checked before session, checkpoint, or approval storage is used,
and a missing platform user ID fails closed. Local requests may remain unscoped.

The Foundry-specific store type intentionally hides the current filesystem
implementation from `ResponsesHostServer` setup. A future version may move
`FoundrySessionStore` to a Foundry storage API without changing the host's
default configuration.
