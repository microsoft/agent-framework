# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

## Security: Hosted Workflow Session Isolation

Hosted workflow checkpoints are mutable session state. `previous_response_id`, `conversation_id`, and `response_id`
identify checkpoint records; they do not authorize checkpoint access by themselves. `ResponsesHostServer` therefore
stamps each hosted workflow checkpoint directory with a hosted session identity context and rejects later resume/write
attempts whose resolved identity does not match.

By default, `ResponsesHostServer` reads the Foundry platform-provided isolation keys from `ResponseContext.isolation`.
If you host workflows outside the Foundry platform, provide `hosted_session_context_resolver=...` that returns a
`HostedSessionContext` derived from your authenticated user and chat/tenant boundary. Do not derive this context only
from untrusted request body fields.

`strict_session_isolation=True` is the default. This rejects hosted workflow checkpoint requests when no identity
context is available. Local-only tests or demos can set `strict_session_isolation=False`, but production multi-user
deployments should keep strict mode enabled and configure a real provider.

### Approval-handle isolation binding

MCP approval handles (`approval_request_id`) are bearer capabilities: anyone who presents one can redeem the
approval-gated tool call. `ResponsesHostServer` therefore binds each saved approval to the same hosted session identity
(`HostedSessionContext`) resolved above, and rejects redemption whose resolved identity does not match the one the
approval was created under — so a handle issued to one user/conversation cannot be replayed from another. The same
`hosted_session_context_resolver` and `strict_session_isolation` settings apply: in strict mode, approval redemption
is rejected when no identity can be resolved.
