# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

`ResponsesHostServer` persists the Agent Framework `AgentSession` used by regular
agents in addition to the Responses provider's message history. By default it
uses the experimental `FoundrySessionStore` under `/.sessions` when hosted and
an in-memory `SessionStore` locally. Hosted snapshots are partitioned by the
Agent Server request context's platform user ID. Snapshot filenames use Responses `response_id` values, with an additional
`conversation_id` snapshot that points to the latest state of each stored
conversation.

Foundry's session file API exposes the hosted `$HOME` directory as `/`, so the
API path `/.sessions` is stored on disk at `$HOME/.sessions`.

Workflow agents use the same continuation model for their checkpoints: every
turn is stored under its `response_id`, and stored conversations also maintain
a `conversation_id` checkpoint alias for their latest turn.

## Foundry session isolation

`FoundrySessionStore` currently subclasses core's `FileSessionStore`. It reads
the active request through `azure.ai.agentserver.core.get_request_context()` and
validates the platform `user_id` (the same `x-agent-user-id` value exposed as
`ResponseContext.platform_context.user_id_key`) before selecting its on-disk
directory.

Regular-agent session snapshots use the platform user ID and a Responses key:

```text
/.sessions/<user-id>/<conversation-id-or-response-id>.json
```

A Foundry session controls hosted compute and filesystem lifetime and may host
multiple users and Responses conversations. The Foundry session ID is not used
as the MAF session identifier.

When `conversation_id` is used, the host reads the latest snapshot under that
ID, then writes the updated state under both the current `response_id` and the
conversation ID. This preserves every turn while keeping conversation
continuation pointed at the latest state. When `previous_response_id` is used,
the host reads that response snapshot, runs the loaded MAF session, and writes
the updated snapshot under the current response's `response_id`. Responses can
therefore branch from any prior turn without overwriting its snapshot,
including turns originally created through a conversation.

Foundry does not infer the hosted `agent_session_id` from
`previous_response_id`. Callers using response chains must also reuse the
`agent_session_id` returned by the previous response so the request reaches the
same sandbox and `$HOME/.sessions` filesystem. Conversation objects bind to a
stable hosted session automatically.

Workflow checkpoints and function approvals preserve the existing Foundry
Hosting roots. Hosted paths insert the validated raw platform user ID:

```text
/.checkpoints/<user-id>/<response-id>/
/.checkpoints/<user-id>/<conversation-id>/
/.function_approvals/<user-id>/approval_requests.json
```

The conversation directory is a latest-state alias. Each response directory
retains the final checkpoint selected for that turn, allowing a later request
to branch from it. Local workflow checkpoints use the same layout without
`<user-id>`, and local function approvals remain in memory.

Hosted requests require container protocol `2.0.0`. The v2-only request
`call_id` is checked before session, checkpoint, or approval storage is used,
and a missing platform user ID fails closed. Regular agents also require the
normal Responses continuation ID for restoration. Local requests may remain
unscoped.

The Foundry-specific store type intentionally hides the current filesystem
implementation from `ResponsesHostServer` setup. A future version may move
`FoundrySessionStore` to a Foundry storage API without changing the host's
default configuration.
