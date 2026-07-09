---
status: proposed
contact: eavanvalkenburg
date: 2026-07-08
deciders: eavanvalkenburg
---

# Python protocol helpers and optional execution state

## Scope

This specification is the Python implementation plan for
[ADR-0027](../decisions/0027-hosting-channels.md). It documents the helper-first v1 contract for Python hosting.

The v1 contract is:

- protocol packages expose helper functions that convert protocol-native input to Agent Framework run values;
- protocol packages expose helper functions that convert Agent Framework run results or streams back to protocol-native
  payloads or operations;
- application/framework code owns routes, native SDK clients, authentication, command policy, webhooks, response status
  codes, and outbound sends;
- `agent-framework-hosting` provides small optional state holders for Agent Framework targets;
- state helpers do not own web apps, route contribution, protocol dispatch, command projection, or native SDK calls.

## Goals

- Let apps expose agents and workflows from FastAPI, Starlette, Django, Azure Functions, native SDK webhooks, CLIs, and
  tests without adopting a host/channel framework.
- Keep protocol parsing and response formatting inside protocol packages.
- Keep session continuity explicit and app-owned at the trust boundary.
- Reuse Agent Framework primitives: `AgentSession`, `CheckpointStorage`, `Agent.run(...)`, `Workflow.run(...)`, and
  `ResponseStream`.
- Preserve full-fidelity Agent Framework results until a protocol helper renders them.

## Non-goals for v1

### App-owned in v1

The app builder owns these concerns with normal web-framework, SDK, platform, or application code:

- authentication, authorization policy, and allowlists;
- deciding whether identities across protocols map to the same `session_id`;
- non-originating sends using native SDK clients;
- background work, durable execution, retry, and replay when app code owns the work;
- routing between multiple agents.

The helper-first model makes app-owned linking and non-originating delivery easier than the old host/channel model because
app code already owns the native SDK clients, authenticated caller context, session id selection, and outbound sends.

### Future framework work

The following require a separate reviewed design before becoming reusable framework features:

- reusable cross-channel identity linking;
- framework-owned proactive or non-originating delivery;
- fan-out, multicast, selected-channel, active-channel, or all-linked delivery;
- framework-owned delivery observability, dead-letter handling, and replay semantics;
- cross-channel confidentiality and link policy.

[ADR-0028](../decisions/0028-hosting-linking-multicast-enhancements.md) tracks possible follow-up work in this area and
must be aligned with the helper-first model before implementation. Old vocabulary such as `IdentityLinker`,
`ResponseTarget`, `ChannelPush`, `ChannelPushCodec`, `DurableTaskRunner`, `RetryPolicy`, and `LinkPolicy` is not v1 API.

## Packages

| Package | Import surface | v1 helper-first contents |
|---|---|---|
| `agent-framework-hosting` | `agent_framework_hosting` | `AgentState`, `WorkflowState`, `SessionStore`, and run-argument `TypedDict`s. |
| `agent-framework-hosting-responses` | `agent_framework_hosting_responses` | Responses helpers: request parsing, session id extraction, response id creation, response rendering, streaming rendering. |
| Future protocol packages | e.g. `agent_framework_hosting_telegram` | Protocol-specific helpers such as `telegram_to_run(...)`, `telegram_from_run(...)`, `telegram_session_id(...)`, and command/media helpers when useful. |

The core hosting package must not depend on protocol SDKs. Protocol packages may depend on their native protocol SDKs if
needed, but helper functions should stay usable from plain app code and tests.

## Helper naming and families

Helper names are protocol-specific. Avoid a generic `protocol_to_run(...)` public surface.

Protocol packages may provide the following helper families when the protocol has the concept:

| Helper family | Shape | Purpose |
| --- | --- | --- |
| Run conversion | `<protocol>_to_run(...)` | Convert one protocol-native call/update/request into `Agent.run` or `Workflow.run` values. |
| Final rendering | `<protocol>_from_run(...)` | Convert a final `AgentResponse` or workflow result into protocol-native response payloads or operations. |
| Stream rendering | `<protocol>_from_streaming_run(...)` | Convert `ResponseStream` or workflow updates into protocol-native events or operations. |
| Session id extraction | `<protocol>_session_id(...)` | Extract the protocol's natural continuation/partition key from the call, if present. |
| Command/action parsing | `<protocol>_command(...)` | Parse a protocol-native command/action/operation name without deciding app policy. |

Examples:

- `responses_to_run(...)`, `responses_from_run(...)`, `responses_from_streaming_run(...)`,
  `responses_session_id(...)`;
- `telegram_to_run(...)`, `telegram_from_run(...)`, `telegram_from_streaming_run(...)`,
  `telegram_session_id(...)`, `telegram_command(...)`;
- `activity_to_run(...)`, `activity_from_run(...)`, `activity_session_id(...)`, `activity_command(...)`;
- `discord_to_run(...)`, `discord_from_run(...)`, `discord_session_id(...)`, `discord_command(...)`.

This table is a naming guide, not a required checklist. A protocol package should add only the helpers that match native
protocol concepts and current samples.

Protocol-specific helpers may also exist for native details such as `telegram_chat_id(...)`,
`telegram_callback_query_id(...)`, `telegram_media_file_id(...)`, `discord_interaction_id(...)`, `a2a_task_id(...)`,
`a2a_context_id(...)`, or MCP tool/prompt/resource helpers. These helpers should stay side-effect-free. App/native SDK
code performs acknowledgements, sends/edits messages, resolves protected file URLs, applies rate limits, and registers
handlers.

## `agent-framework-hosting` state helpers

### `SessionStore`

`SessionStore` is an in-memory async lookup:

```python
class SessionStore:
    async def get(self, session_id: str) -> AgentSession | None: ...
    async def set(self, session_id: str, session: AgentSession) -> None: ...
    async def delete(self, session_id: str) -> None: ...
```

The store does not create sessions. It stores `session_id -> AgentSession` values supplied by callers.

The built-in store has no TTL or eviction. This is intentional for local/dev and simple process-local scenarios: protocols
such as OpenAI Responses can continue from any prior response id. Durable or multi-replica deployments should provide a
durable store and their own TTL/eviction policy.

### `AgentState`

`AgentState` holds an agent target and an optional `SessionStore`:

```python
state = AgentState(agent)
state = AgentState(create_agent)
state = AgentState(create_agent, cache_target=False)
```

The target may be:

- a `SupportsAgentRun` instance;
- a synchronous factory;
- an asynchronous factory;
- an awaitable target.

`AgentState` provides:

- `await get_target()`;
- synchronous `target` only after a target is already available/resolved;
- `session_store`;
- `await get_or_create_session(session_id)`;
- `await set_session(session_id, session)`.

`get_or_create_session(...)` resolves the target and calls `target.create_session(session_id=...)` only when the store has
no session for that id.

Apps must store the post-run session explicitly after `agent.run(...)` or stream finalization:

```python
session = await state.get_or_create_session(session_id)
target = await state.get_target()
result = await target.run(messages, session=session, options=options)
await state.set_session(response_id, session)
```

### `WorkflowState`

`WorkflowState` resolves a workflow target. It does not own checkpoint storage.

The target may be:

- a `Workflow` instance;
- a `WorkflowBuilder` or other object with `build() -> Workflow`;
- a synchronous factory;
- an asynchronous factory;
- an awaitable target.

`WorkflowState` provides:

- `await get_target()`;
- synchronous `target` only after a target is already available/resolved.

Workflow checkpointing uses Agent Framework's existing `CheckpointStorage` abstraction directly. Apps that need
per-session workflow resume should keep an app-owned cursor such as `session_id -> checkpoint_id`. When the app uses
file-backed cursor storage, the file-based checkpoint storage should share the same app storage root and should be
scoped to the current authenticated user/tenant/session bucket, for example
`storage/checkpoints/<session-bucket>/` beside `storage/checkpoint_cursors.json`:

```python
# session_id must already be authenticated and authorized for this caller
target = await workflow_state.get_target()
checkpoint_id = await checkpoint_cursor_store.get(session_id)
if checkpoint_id is None:
    result = await target.run(message=workflow_input, checkpoint_storage=checkpoint_storage)
else:
    result = await target.run(checkpoint_id=checkpoint_id, checkpoint_storage=checkpoint_storage)
latest = await checkpoint_storage.get_latest(workflow_name=target.name)
if latest is not None:
    await checkpoint_cursor_store.set(session_id, latest.checkpoint_id)
```

`Workflow.run(...)` does not currently emit a checkpoint id on `WorkflowRunResult` or normal workflow events by default.
The runner receives checkpoint ids internally from `CheckpointStorage.save(...)`. Apps that own the storage can query
`get_latest(workflow_name=...)` after the run if they need to update a cursor.

## `agent-framework-hosting-responses`

The Responses package provides the helper-first surface for OpenAI Responses-shaped requests.

### Request helpers

- `messages_from_responses_input(input) -> list[Message]`
- `responses_to_run(body) -> AgentRunArgs`
- `responses_session_id(body) -> str | None`
- `create_response_id() -> str`

`responses_to_run(...)` returns values corresponding to `Agent.run(...)`:

```python
run = responses_to_run(body)
messages = run["messages"]
options = run["options"]
stream = run["stream"]
```

It excludes protocol transport/session fields from `options` and remaps known Responses option names such as
`max_output_tokens -> max_tokens`.

`responses_session_id(...)` returns:

- `previous_response_id` when present (`resp_*`);
- otherwise `conversation_id` when present (`conv_*`);
- otherwise `None`.

The helper only extracts the candidate key. App code decides whether to trust and use that key.

### Response helpers

- `responses_from_run(result, *, response_id, session_id=None) -> dict[str, Any]`
- `responses_from_streaming_run(stream, *, response_id, session_id=None) -> AsyncIterator[str]`

`responses_from_run(...)` renders a full Responses JSON payload from an `AgentResponse`. It renders the full set of
OpenAI Responses output item types supported by Agent Framework content.

`responses_from_streaming_run(...)` renders Server-Sent Event strings for a `ResponseStream`. It emits a created event,
text deltas, and a completed event. The final completed payload is produced through `responses_from_run(...)`; the helper
also preserves the model id observed on streaming updates when the finalized `AgentResponse` no longer carries raw model
metadata.

## Security responsibilities

Protocol helper packages parse and render. They do not authenticate callers, authorize access to state, or decide which
side effects are allowed.

Application code that uses these helpers is responsible for:

- authenticating the caller through the app's normal mechanism before using protocol-provided ids;
- authorizing any caller-supplied session, checkpoint, task, context, conversation, thread, or response id before loading
  state for it;
- binding externally supplied ids to the authenticated user, tenant, workspace, installation, or chat context before
  using them as `SessionStore` keys or checkpoint cursor keys;
- treating `<protocol>_session_id(...)` results as untrusted candidate keys until that ownership check has passed;
- keeping platform-provided isolation helpers fail-closed outside their trusted hosting environment;
- authorizing command/action effects such as reset, cancel, approve, submit, or tool invocation after parsing them;
- opting in explicitly before resolving protected media/resource/file URLs and passing them to a remote model provider;
- persisting post-run session or checkpoint state only after `agent.run(...)`, `workflow.run(...)`, or stream finalization
  has updated that state.

## Persistent versus transient hosting

The application builder decides whether the server is persistent or transient.

- Persistent single-process apps, such as a long-running container or web app, may use in-memory state for local
  development or simple deployments. Multi-replica persistent apps still need durable state for continuity.
- Transient apps, such as Azure Functions, Foundry Hosted Agents, or any environment where process memory is not a
  reliable boundary, must not rely on in-memory `SessionStore` state between calls. They need a durable session store or
  a service-owned continuation id.
- Workflow hosts must choose an explicit `CheckpointStorage` and, when they need per-session resume, a durable
  `session_id -> checkpoint_id` cursor. File-backed checkpoint storage and file-backed cursor storage should live under
  the same app storage root, with checkpoints scoped to the current authenticated user/tenant/session bucket so a
  "latest checkpoint" lookup cannot cross conversations. In-process workflow state and in-memory checkpoint cursors do
  not survive transient execution.

## Minimal FastAPI Responses shape

This is the shape the local Responses sample should demonstrate. It is not an app framework.

```python
from collections.abc import AsyncIterator

from agent_framework import ResponseStream
from agent_framework_hosting import AgentState
from agent_framework_hosting_responses import (
    create_response_id,
    responses_from_run,
    responses_from_streaming_run,
    responses_session_id,
    responses_to_run,
)
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
state = AgentState(create_agent)


@app.post("/responses", response_model=None)
async def responses(body: dict = Body(...)) -> JSONResponse | StreamingResponse:
    run = responses_to_run(body)
    candidate_session_id = responses_session_id(body)
    response_id = create_response_id()

    # Verify this caller owns candidate_session_id before loading it.
    session_id = candidate_session_id or response_id
    session = await state.get_or_create_session(session_id)
    target = await state.get_target()

    if run["stream"]:
        stream = target.run(run["messages"], stream=True, session=session, options=run["options"])
        if not isinstance(stream, ResponseStream):
            raise HTTPException(status_code=500, detail="agent did not return a response stream")

        async def events() -> AsyncIterator[str]:
            async for event in responses_from_streaming_run(
                stream,
                response_id=response_id,
                session_id=candidate_session_id,
            ):
                yield event
            await state.set_session(response_id, session)

        return StreamingResponse(events(), media_type="text/event-stream")

    result = await target.run(run["messages"], session=session, options=run["options"])
    await state.set_session(response_id, session)
    return JSONResponse(responses_from_run(result, response_id=response_id, session_id=candidate_session_id))
```

## Validation

Implementation validation must cover:

- `SessionStore` plain get/set/delete behavior;
- `AgentState` target resolution, target caching, and get-or-create session behavior;
- `WorkflowState` target resolution for direct workflows, factories, `WorkflowBuilder`, and orchestration-style builders;
- Responses request parsing and option remapping;
- Responses session id extraction;
- Responses response rendering, including rich output item mapping;
- Responses streaming SSE rendering;
- HTTP round-trip tests showing a native FastAPI route using `AgentState` and Responses helpers;
- sample type checking for the local Responses sample.
