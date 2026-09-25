# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

## Agent instances and factories

`ResponsesHostServer` and `InvocationsHostServer` accept an agent instance or a zero-argument callable through the
existing `agent` parameter. The callable may be synchronous or asynchronous, must return an object implementing
`SupportsAgentRun`, and is invoked once for each request:

```python
server = ResponsesHostServer(agent=create_agent)
```

Passing an instance reuses that object for the lifetime of the host. Pass a callable when the agent keeps mutable state
outside `AgentSession`. In particular, a `WorkflowAgent` wraps a stateful workflow, so its callable should build a new
workflow, executors, and wrapped agents. Keep the workflow name and executor IDs stable so later requests can find and
restore its checkpoints:

```python
def create_agent():
    return build_workflow().as_agent()


server = ResponsesHostServer(agent=create_agent)
```

The Responses host continues regular agents through its existing session store and workflow agents through its
existing checkpoint store. A callable does not make arbitrary instance fields persistent; state needed by later
requests must remain in the supported stores.

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

`ResponsesHostServer` owns a supplied agent instance and may add hosting-specific context providers. Do not reuse that
instance with another host or invoke it directly after constructing the server. An agent returned by a callable belongs
to that request.

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

Hosted requests take their sandbox session ID, user ID, and call ID from the trusted
AgentServer request context. All three are required; IDs in a caller's Responses or
Invocations payload cannot stand in for missing platform identity. The exported
`FoundryRequestScope.from_context(config, platform_context)` validates this identity.
Its `storage_key` is a bounded hash of the framed user and sandbox IDs, not a caller
conversation or response ID.

| Identifier | Purpose |
| --- | --- |
| Foundry session ID | Platform sandbox for the hosted request and its MAF state. |
| Platform user ID / call ID | User isolation and per-request storage authorization/correlation. A call ID is **not** a conversation ID. |
| Responses `response.id`, `previous_response_id`, `conversation` | Caller-visible continuation and conversation IDs, used as item keys *within* the sandbox. |
| MAF `AgentSession.session_id` / `service_session_id` | Inner agent state and optional downstream service continuation; neither identifies the Foundry sandbox. |
| Workflow checkpoint ID | Inner workflow state within a checkpoint context, not a Foundry session ID. |

The default hosted MAF session, checkpoint, and approval stores use a `v2` namespace
derived from the hashed platform identity, with `user_isolation=True` and an explicit
platform `call_id` on each item operation. Checkpoint context IDs are hashed as well.
The same user in two hosted sandboxes cannot read the other's default MAF state.
Locally, the existing single-user store names and file-based fallback remain unchanged;
direct store constructors without a trusted `scope` also retain their existing local
behavior. Applications that supply custom store providers must implement equivalent
hosted user and sandbox isolation.

**Existing hosted state is not migrated.** The default stores never fall back to
legacy unscoped `agent_sessions`, `checkpoints/<context_id>`, or
`function_approvals` data: an old MAF session, workflow checkpoint, or pending approval
cannot be resumed through the new default hosted stores. Start a fresh Responses
conversation rather than reusing an old `previous_response_id` or conversation ID;
the separate AgentServer response store is not migrated by this change. Recovering
old state requires a separately designed migration that verifies the original user's
and sandbox's ownership; reading unscoped data by user alone is not safe.

### Agent Sessions

`ResponsesHostServer` persists the Agent Framework `AgentSession` durably. By default it
uses the `FoundryAgentSessionStore`, backed by Foundry storage when hosted and file-based
storage locally. Stored sessions are scoped under `agent_sessions`.

Loaded MAF sessions are saved with an ETag condition. A competing turn that has
already advanced the same conversation causes a visible persistence failure instead
of silently overwriting its state. New hosted session keys are created only if absent;
turns using `previous_response_id` write their own new response ID, without applying
the predecessor's ETag to a different key. Local callers can still upsert directly
without first loading a session.

See the [custom storage provider sample](../../samples/04-hosting/foundry-hosted-agents/responses/custom_storage/)
for an example that uses an in-memory session store locally and Azure Cosmos DB when hosted.

Native Responses refusal parts are stored as text carrying
`additional_properties["model_output_kind"] == "refusal"` and emitted as
`response.refusal.*` events when streamed back to clients.

`InvocationsHostServer` keeps sessions in memory. When hosted, `AgentSession.session_id` is an
opaque composite identifier that preserves the boundaries between the platform session ID
and user ID. Consumers must use it as a whole and must not parse it or depend on its internal
representation. Repeated requests for the same identifier pair reuse the session. Locally,
the platform session ID is used unchanged.

### Workflow checkpoints

`ResponsesHostServer` persists workflow checkpoints durably. By default, it uses the
`FoundryCheckpointStore`, backed by Foundry storage when hosted and file-based storage
locally. Stored checkpoints are scoped under `checkpoints`.

### Function approvals

`ResponsesHostServer` persists function approvals durably. By default, it uses the
`FoundryFunctionApprovalStore`, backed by Foundry storage when hosted and file-based
storage locally. Stored approvals are scoped under `function_approvals`.
