# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

`ResponsesHostServer` persists the Agent Framework `AgentSession` used by regular
agents in addition to the Responses provider's message history. By default it
uses the experimental `FoundrySessionStore` under `/.sessions` when hosted and
an in-memory `SessionStore` locally. Hosted snapshots are partitioned by the
Agent Server request context's platform user ID, and their filenames come from
its platform session ID. Pass `session_store=` to explicitly override either
default.

Foundry's session file API exposes the hosted `$HOME` directory as `/`, so the
API path `/.sessions` is stored on disk at `$HOME/.sessions`.

Workflow agents continue to use their existing checkpoint storage layout.

## Foundry session isolation

`FoundrySessionStore` currently subclasses core's `FileSessionStore`. It reads
the active request through `azure.ai.agentserver.core.get_request_context()` and
validates the platform `user_id` (the same `x-agent-user-id` value exposed as
`ResponseContext.platform_context.user_id_key`) before selecting its on-disk
directory.

Regular-agent session snapshots use the platform user and session IDs:

```text
/.sessions/<user-id>/<session-id>.json
```

Workflow checkpoints and function approvals preserve the existing Foundry
Hosting layout. Hosted paths insert the validated raw platform user ID:

```text
/.checkpoints/<user-id>/<context-id>/
/.function_approvals/<user-id>/approval_requests.json
```

Local workflow checkpoints use `{cwd}/.checkpoints/<context-id>/`, and local
function approvals remain in memory.

Hosted requests require container protocol `2.0.0`. The v2-only request
`call_id` is checked before session, checkpoint, or approval storage is used,
and a missing platform user ID fails closed. Regular agents also require the
platform session ID used for their snapshot filename. Local requests may remain
unscoped.

The Foundry-specific store type intentionally hides the current filesystem
implementation from `ResponsesHostServer` setup. A future version may move
`FoundrySessionStore` to a Foundry storage API without changing the host's
default configuration.
