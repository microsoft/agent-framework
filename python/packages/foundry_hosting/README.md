# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

## State store

### Agent Sessions

`ResponsesHostServer` persists the Agent Framework `AgentSession` durably. By default it
uses the `FoundryAgentSessionStore` when hosted and an in-memory `SessionStore` locally.
When hosted, the stored sessions will be isolated by the platform user ID and scoped
under `agent_sessions`.

### Workflow checkpoints

`ResponsesHostServer` persists workflow checkpoints durably. By default, it uses the
`FoundryCheckpointStore` when hosted and an in-memory `InMemoryCheckpointStorage` locally.
When hosted, the stored checkpoints will be isolated by the platform user ID and scoped
under `checkpoints`.

### Function approvals

`ResponsesHostServer` persists function approvals durably. By default, it uses the
`FoundryFunctionApprovalStore` when hosted and an in-memory `InMemoryFunctionApprovalStore` locally. When hosted, the stored approvals will be isolated by the platform user ID and scoped under `function_approvals`.