# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

## Conversation history

`ResponsesHostServer` uses AgentServer response history as the model's conversation history by default:

```python
server = ResponsesHostServer(agent)
```

In this mode, the configured AgentServer response provider supplies the prior transcript. Hosting rejects
`HistoryProvider` instances with `load_messages=True` and agents configured with a default `conversation_id`,
`previous_response_id`, or `conversation`, adds a transient in-memory provider for function-call loops, and clears
restored downstream service IDs. For clients that advertise `STORES_BY_DEFAULT=True`, hosting forces downstream
`store=False`; for other clients it removes an explicit agent-level `store` option and does not forward one. These
safeguards ensure the model receives the transcript once without sending unsupported storage options.

AgentServer history requires a framework `RawAgent` whose client declares the boolean `STORES_BY_DEFAULT` capability;
the agent's runtime options then let hosting enforce downstream storage behavior. Custom `SupportsAgentRun`
implementations must use `history_source="agent"` because that protocol does not accept runtime chat options.

`ResponsesHostServer` owns the supplied agent instance and may add hosting-specific context providers. Do not reuse that
agent with another host or invoke it directly after constructing the server.

To preserve the agent's regular history and service-storage behavior, select the agent as the history source:

```python
server = ResponsesHostServer(agent, history_source="agent")
```

Hosting then passes only current request input, allows load-enabled history providers, and does not override the
agent's downstream `store` option. For example, `InMemoryHistoryProvider` stores messages in `AgentSession.state`, which
the default `FoundryAgentSessionStore` persists in Foundry:

```python
agent = Agent(
    client=client,
    context_providers=[InMemoryHistoryProvider()],
    default_options={"store": False},
)
server = ResponsesHostServer(agent, history_source="agent")
```

The `store` argument remains independent: it selects the AgentServer response provider used for Responses API
persistence and retrieval. Omitting it or passing `None` selects the environment default. With
`history_source="agent_server"`, that response provider also supplies model history; with `history_source="agent"`, it
does not.

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

Native Responses refusal parts are stored as text carrying
`additional_properties["model_output_kind"] == "refusal"` and emitted as
`response.refusal.*` events when streamed back to clients.

### Workflow checkpoints

`ResponsesHostServer` persists workflow checkpoints durably. By default, it uses the
`FoundryCheckpointStore`, backed by Foundry storage when hosted and file-based storage
locally. Stored checkpoints are scoped under `checkpoints`.

### Function approvals

`ResponsesHostServer` persists function approvals durably. By default, it uses the
`FoundryFunctionApprovalStore`, backed by Foundry storage when hosted and file-based
storage locally. Stored approvals are scoped under `function_approvals`.
