# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

## Agent instances and factories

Both hosts accept either an ordinary agent instance or an `agent_factory`, but not both.
Existing `ResponsesHostServer(agent)` and `InvocationsHostServer(agent)` calls remain supported for ordinary agents.
Pass `WorkflowAgent` and `FunctionalWorkflowAgent` through a factory instead of passing a live instance:

```python
from agent_framework_foundry_hosting import InvocationsHostServer, ResponsesHostServer


def create_agent():
    # Build a new workflow, with new mutable agents and executors, here.
    return build_workflow().as_agent()


server = ResponsesHostServer(agent_factory=create_agent)
# Alternatively, use the existing Invocations text protocol:
# server = InvocationsHostServer(agent_factory=create_agent)
```

A factory takes no arguments and can return an agent directly or await its construction:

```python
async def create_agent():
    configuration = await load_configuration()
    return build_workflow(configuration).as_agent()


server = ResponsesHostServer(agent_factory=create_agent)
```

The host calls the factory inside the current request's platform context, not during startup. The resulting agent
belongs to that request, including its entire stream. Responses recovery also creates a new agent through the factory.
Returning the same workflow instance repeatedly is not supported. Neither is building a new workflow around previously
used mutable executors. Keep workflow names, executor IDs, and serialized state type registrations stable so a new
instance can restore the previous instance's checkpoints.

Factories are also useful for ordinary agents with request-specific configuration. They do not automatically persist
custom fields on an agent: state needed on the next request must use the supported session or checkpoint stores.
The host recognizes the two built-in workflow adapters and their subclasses; it cannot discover a workflow hidden
inside an arbitrary custom agent.

### Resource ownership

The host enters and exits a factory-created agent's async context manager when it has one. Resources remain available
until execution and streaming finish, and are released on completion or interruption. Factory code must clean up its
own partially constructed resources if it fails before returning an agent.

Built-in workflow adapters do not automatically close every client or tool captured by their executors. Keep
application-owned, concurrency-safe clients open for the host lifetime, or return a workflow subclass with an async
context manager that owns its request-specific resources. Do not close a shared client at the end of one request.
An ordinary `Agent` context manager also manages its chat client and MCP tools, so their ownership must match its lifetime.

See the [workflow sample](../../samples/04-hosting/foundry-hosted-agents/responses/workflows/) for fresh agents and
executors using an application-owned model client, and the
[recovery sample](../../samples/04-hosting/foundry-hosted-agents/responses/resilient_long_running_workflow/)
for request-local workflows restored after a process restart.

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

Each factory-created workflow starts with independent runtime state. Responses restores only the checkpoint belonging
to the current user and conversation or response chain. A `previous_response_id` without a saved workflow checkpoint
fails; a conversation with prior history but no workflow checkpoint also fails rather than silently starting over.
A new conversation with no history can start without a checkpoint.

For resilient background Responses using a graph workflow, recovery uses the checkpoint associated with the persisted response output.
If no response checkpoint was recorded, it can use the latest workflow checkpoint. If execution stopped before any
workflow checkpoint was saved, recovery replays the original input using a fresh factory-created workflow.

`FunctionalWorkflowAgent` does not support `resilient_background=True`. Its checkpoints retain completed step results
but not all output buffered inside those steps. Recovering from such a checkpoint could omit output; the host rejects
that configuration instead of silently losing output or rerunning application work. Functional workflows can use
the factory for normal Responses requests and supported pending-response continuation.

### Invocations workflows

`InvocationsHostServer(agent_factory=...)` persists workflow checkpoints for the platform user and invocation session.
A subsequent request with the same authorized session can restore its graph workflow in a new agent instance, including
after recreating the host. Ordinary-agent instance callers retain their existing in-memory session behavior.

The wire format remains unchanged: requests use `message` and `stream`, and responses contain text or streamed text.
This helper does not add a structured exchange for external workflow approvals or pending requests. A plain text
message is not an approval response. Use Responses when callers need that structured exchange.

Functional workflows accept a new message after a completed invocation, but pending or interrupted functional
continuation is rejected. They do not acquire graph-workflow recovery semantics by being passed through a factory.

Requests updating the same workflow scope are serialized within one host; independent scopes can execute concurrently.
This is not a distributed lock across multiple host processes. Invocations does not automatically recover an
interrupted HTTP response, and checkpoints do not guarantee that external side effects execute exactly once.

### Function approvals

`ResponsesHostServer` persists function approvals durably. By default, it uses the
`FoundryFunctionApprovalStore`, backed by Foundry storage when hosted and file-based
storage locally. Stored approvals are scoped under `function_approvals`.
