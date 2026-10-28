# Invocations agent with a custom request parser

[`main.py`](main.py) hosts an Agent Framework agent using the Foundry
Invocations protocol. The sample accepts application JSON with a `prompt`
field rather than the host's default `message` field. Its `parse_request`
callback returns `InvocationRun(messages, options, stream)`, and
`prepare_options` allows only `temperature` and `max_tokens` from the caller.
The host also rejects platform IDs, `store`, and private continuation options
even if a hook tries to return them. The agent keeps `store=False` as a
developer default; caller options cannot enable service-managed history.

**Invocations does not store conversation history.** The sample's
`InMemoryHistoryProvider` keeps model messages in the MAF `AgentSession`, which
the host saves in its separate `invocation_sessions` store. That store uses
files locally and Foundry state storage when hosted. A later turn, even in a
replacement host process, restores the history from the same trusted user and
sandbox. Sandbox files remain in the Foundry sandbox; they are not part of
the MAF session.

## Run and invoke

Follow the [parent guide](../../README.md#running-the-agent-host-locally)
to run the sample locally. Send a non-streaming request:

```bash
curl -i -X POST http://localhost:8088/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hi", "options": {"temperature": 0.3}}'
```

The default wire format is JSON, for example:

```http
HTTP/1.1 200 OK
content-type: application/json
x-agent-session-id: 9370b9d4-cd13-4436-a57f-03b843ac0e17

{"response":"Hi! How can I help?"}
```

To continue in that sandbox, put the returned **platform**
`x-agent-session-id` in the Invocations **query parameter**:

```bash
curl -i -N -X POST \
  "http://localhost:8088/invocations?agent_session_id=9370b9d4-cd13-4436-a57f-03b843ac0e17" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What did I say earlier?", "stream": true}'
```

Streaming uses framed server-sent events (`text/event-stream`):

```text
event: delta
data: {"text": "You said hi."}

event: done
data: {"session_id": "9370b9d4-cd13-4436-a57f-03b843ac0e17"}
```

The `done` ID is the **sandbox ID**, not the MAF `AgentSession.session_id`.
On Foundry, the query ID routes the request to the sandbox; a body field does
not. The host requires trusted platform user and call IDs. If
`FOUNDRY_AGENT_SESSION_ID` is absent, even the first hosted request requires
an explicit query ID matching the routed request context (for example,
[create a hosted session first](https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-sessions)).
If the environment ID is present, a different query ID is rejected. Local
requests retain the SDK's single-user generated-ID fallback. See the
[state-store guide](../../../../../packages/foundry_hosting/README.md#state-store)
for scope and retention details.

Malformed requests return JSON client errors. Streaming failures produce
`event: error` instead of `done`; a competing host's session write is reported
as a conflict, not silently overwritten. Do not blindly retry calls with
non-idempotent tools. Existing clients that still require the old plain-text
response and raw text-chunk stream can set `legacy_wire_format=True` on the
host temporarily; the host warns once and the mode is deprecated. Migrate
clients to JSON and framed SSE before removing that opt-in in a deliberate
breaking change.

Follow the [parent deployment guide](../../README.md#deploying-the-agent-to-foundry)
when deploying this example to Foundry.

## Native workflow with typed tickets

[`workflow.py`](workflow.py) is an alternative entrypoint, not a wrapper around
the agent above. It hosts a native `Workflow` with
`InvocationsHostServer(workflow=build_workflow, parse_request=parse_request)`;
there is no `workflow.as_agent()`. Its deterministic ticket/review executors
need no model deployment or Azure credentials locally.

The application parser validates its own JSON and returns a
`WorkflowTurn(input=Ticket(...), stream=...)` or
`WorkflowTurn(responses={request_id: TicketDecision(...)}, stream=...)`.
The parser checks reply types; the host separately checks that each reply
belongs to the exact pending checkpoint in the trusted sandbox and user.
It rejects unknown fields rather than forwarding caller-controlled
instructions, tools, middleware, session IDs or tool context as run options.
When adding agents or tools, keep their defaults and trusted context in the
request-aware factory. `client_kwargs` and `function_invocation_kwargs` keep
their existing workflow meanings; they are not arbitrary entry-state updates.

Use the current workspace until the coordinated hosting beta containing the
native workflow API is published. From `python/`, run:

```bash
uv run --no-sync python samples/04-hosting/foundry-hosted-agents/invocations/basic/workflow.py
```

After that release, the script's PEP 723 metadata also supports
`uv run --script --prerelease=allow workflow.py`. Do not change a
`pyproject.toml` to install sample-only imports. This entrypoint does not read
a `.env` file.

### Application JSON and SSE

For an immediate typed result, opt out of review:

```bash
curl -i -X POST http://localhost:8088/invocations \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"T-1","question":"Where is my order?","require_review":false}'
```

Non-streaming workflow responses are application JSON, with typed payloads in
the `output` event list. A ticket produces a result containing its
`ticket_id`, persisted `turn` number and `status`. Dataclasses, Pydantic models
and framework `Message`, `Content` and `AgentResponse` values retain their
supported structured encoding; they are not coerced to text. Unsupported
objects fail visibly instead of being stringified or omitted.

By default, tickets pause for a review. Send a new ticket with
`"stream": true` to receive framed `request_info` SSE containing a `request_id`
and the typed ticket review. Reuse that ID in the next request:

```bash
curl -i -N -X POST \
  "http://localhost:8088/invocations?agent_session_id=<sandbox-id>" \
  -H "Content-Type: application/json" \
  -d '{"responses":{"<request-id>":{"approved":true}},"stream":true}'
```

The reply emits an `output` event with status `approved` (or `rejected` for
`false`). A final `done` event contains the platform `session_id`, and is
emitted only after the exact workflow cursor has been conditionally saved.
Live output is provisional until `done`. Authority-bearing `request_info`
frames and any following frames are buffered until the cursor is committed,
so emitted request IDs refer to durable pending state.
If the connection drops after commit, retry the request with the same trusted
user, sandbox and platform call ID to replay the complete stored response
without executing the ticket workflow again.
Failures produce `error`, not `done`. Non-streaming pauses expose the same
`request_info` data in the JSON event list. Native workflows do not support
`legacy_wire_format=True`; the old plain-text/raw-chunk opt-in applies only
to the agent entrypoint.

### Checkpoints, fresh factories and pending replies

`build_workflow(request)` builds fresh executors on every request. The graph
name `ticket-workflow` and executor ID `ticket_start` remain stable. Typed
`TicketState` is saved in workflow state through `ctx.set_state`, and restored
from the exact prior checkpoint even after replacing the host process. The
checkpoint provider explicitly allowlists this example's application types
for decoding; it does not load arbitrary caller-specified Python classes.
An incompatible graph is rejected before dispatch. Do not configure a
second checkpoint store on `WorkflowBuilder` or share a mutable workflow
instance between requests.

Finish pending reviews before submitting another ticket. Replies cannot
invent a request ID, cross users or sandboxes, replay an already-consumed
request, or reuse a stale checkpoint's authority. If a graph has multiple
pending requests, answer the **complete batch** in one turn. Partial or
invalid batches are rejected before any reply is consumed or handler runs;
resubmit the complete valid batch. A failed or interrupted turn does not
report successful completion. Its claimed lineage is blocked instead of
replaying possibly completed effects; start a new Foundry sandbox.
Conditional storage
conflicts are visible; checkpoints do not provide exactly-once external tool
side effects, so use idempotent application actions.

Continue using the **platform** sandbox ID from `x-agent-session-id` in the
`agent_session_id` query. It routes to the Foundry sandbox, whereas MAF
checkpoints and pending request IDs identify state *inside* that sandbox.
Body/header IDs cannot change platform routing. Hosted requests also require
trusted user and call IDs; without `FOUNDRY_AGENT_SESSION_ID`, use an explicitly
created hosted session and a matching routed query, as described above.
Local requests retain the SDK's single-user session fallback.

For hosted deployment, use the parent guide with `workflow.py` as the Python
entrypoint (or the container command). The existing basic manifest and
Dockerfile still launch `main.py`; change the entrypoint deliberately rather
than expecting this alternative to replace the agent sample.
