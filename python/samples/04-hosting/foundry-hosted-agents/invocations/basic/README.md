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
