# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

## State store

### Local persistence

Outside the Foundry hosting environment, state is persisted as JSON files under
`~/.agentserver/state_stores` by default. Set `AGENTSERVER_STATE_ROOT` to use a
different root directory; the files will be written to its `state_stores`
subdirectory instead.

Each logical store is saved as one JSON file whose name is a URL-safe Base64
encoding of the store name. For example:

- Agent sessions: `YWdlbnRfc2Vzc2lvbnM.json`
- Function approvals: `ZnVuY3Rpb25fYXBwcm92YWxz.json`
- Workflow checkpoints: one file per context, encoded from `checkpoints/<context_id>`

> Read more about the Foundry durable state store in the [developer guide](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/agentserver/azure-ai-agentserver-core/docs/state-store-guide.md).

### User isolation

When hosted on Foundry, the default state stores automatically isolate data by the
platform user ID supplied with each request. Sessions, workflow checkpoints, and
function approvals written for one user cannot be read or modified by another user.
No additional partitioning configuration is required when using the default stores.

### Agent Sessions

`ResponsesHostServer` persists the Agent Framework `AgentSession` durably. By default it
uses the `FoundryAgentSessionStore`, backed by Foundry storage when hosted and file-based
storage locally. Stored sessions are scoped under `agent_sessions`.

See the [custom storage provider sample](../../samples/04-hosting/foundry-hosted-agents/responses/custom_storage/)
for an example that uses an in-memory session store locally and Azure Cosmos DB when hosted.

### Workflow checkpoints

`ResponsesHostServer` persists workflow checkpoints durably. By default, it uses the
`FoundryCheckpointStore`, backed by Foundry storage when hosted and file-based storage
locally. Stored checkpoints are scoped under `checkpoints`.

### Function approvals

`ResponsesHostServer` persists function approvals durably. By default, it uses the
`FoundryFunctionApprovalStore`, backed by Foundry storage when hosted and file-based
storage locally. Stored approvals are scoped under `function_approvals`.
