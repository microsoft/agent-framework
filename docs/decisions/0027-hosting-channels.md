---
status: accepted
contact: eavanvalkenburg
date: 2026-06-30
deciders: eavanvalkenburg
---

# Python protocol helpers and optional execution state

## Context and Problem Statement

Agent Framework needs to help applications expose agents and workflows over external protocols such as OpenAI
Responses, Telegram, Activity Protocol, and future transports.

The first version of this ADR chose a host/channel model: channel packages contributed routes, middleware, commands,
lifecycle callbacks, hooks, and protocol dispatch to a common host object. That design was accepted before it was
released. Implementation experiments showed that the most valuable part is narrower: translating protocol-native
payloads into Agent Framework inputs and translating Agent Framework results back to protocol-native payloads.

FastAPI, Starlette, Azure Functions, Django, Telegram SDKs, Bot Framework SDKs, and other app frameworks already own
route registration, dependency injection, middleware, authentication, background tasks, lifecycle, and native client
calls. Agent Framework should not duplicate those surfaces unless a specific hosting environment requires it.

## Decision Drivers

- Keep the released surface small enough to explain without first teaching a channel framework.
- Provide reusable Agent Framework run translation that works with FastAPI and other web frameworks.
- Let app/framework code own route declaration, auth, middleware, native SDK clients, command handling, and background
  work.
- Keep stateful execution support explicit: session lookup/storage and workflow checkpoint lookup/storage may still need
  a small AF-owned home.
- Avoid approving cross-channel identity and delivery semantics before their safety model is reviewed.

## Considered Options

1. Create protocol-specific hosts.
2. Ship a full host/channel framework with route contribution and channel hooks.
3. Ship protocol conversion helpers plus optional execution state.

### Create protocol-specific hosts

- Good: no new shared abstraction.
- Neutral: each protocol host can evolve independently.
- Bad: every package reinvents AF input/result mapping, session-key conventions, and stateful execution helpers.

### Ship a full host/channel framework

- Good: one object can assemble routes, channels, session handling, hooks, and lifecycle callbacks.
- Good: app code using the supported host shape can be short.
- Bad: the framework owns concerns already handled by web frameworks, protocol SDKs and/or other services.
- Bad: users must understand `Channel`, contribution, hook, and host-dispatch concepts before they can see how a request
  becomes `agent.run(...)`.
- Bad: the abstraction is hard to reuse outside the chosen ASGI shape.

### Ship protocol helpers plus optional execution state

- Good: protocol packages provide the Agent Framework run value directly: `<protocol>_to_run(...)` and
  `<protocol>_from_run(...)` style helpers.
- Good: apps keep native FastAPI, Starlette, Azure Functions, Django, Bot Framework, or Telegram SDK code.
- Good: helper functions can be tested without an ASGI app or host pipeline.
- Good: small state objects can still own target-coupled state: `AgentState` pairs an agent target with a `SessionStore`,
  and `WorkflowState` pairs a workflow target with a `CheckpointStore`.
- Good: provides maximum configurability in handling input and outputs (outside of the conversions)
- Bad: building a first iteration of a new Host is more verbose.
- Bad: samples show more explicit route/client code than a fully assembled channel host.

## Decision Outcome

Chosen option: **protocol helpers plus optional execution state**.

Protocol packages own:

- parsing protocol-native input into Agent Framework run input and options;
- rendering `AgentResponse`, `AgentResponseUpdate`, workflow results, or workflow updates back into protocol-native
  response/event payloads;
- protocol-specific isolation/session id helper functions when useful, such as `telegram_session_id(update)`;
- protocol-specific typing/update event helpers where the protocol has a native concept.

Application or web-framework code owns:

- HTTP route declaration and route grouping;
- dependency injection;
- authentication and authorization;
- middleware;
- background tasks and webhook acknowledgement policy;
- native protocol SDK clients and outbound calls;
- command registration and command dispatch;
- request/response status codes and framework-specific error handling;
- choosing the isolation/session id source for the current deployment and route.

The optional execution-state helpers, if provided, are limited to shared execution state:

- `AgentState`: one `SupportsAgentRun`-compatible target plus a `SessionStore`;
- `WorkflowState`: one `Workflow`, `WorkflowBuilder`-shaped builder, orchestration builder, or workflow factory plus a
  `CheckpointStore`;
- `SessionStore` and `CheckpointStore`: plain async storage (`get` / `set` / `delete`) by an app-selected id.

The stores do not create sessions or checkpoint storage. State objects provide the target-aware helpers
(`AgentState.get_or_create_session(...)`, `WorkflowState.get_or_create_checkpoint_storage(...)`) because only the state
object has both the store and the resolved target.

These objects are **not** app objects, channel registries, or route owners. They do not own FastAPI/Starlette setup,
route contribution, protocol dispatch, command projection, or native SDK calls.

### Helper naming and families

Helpers should be protocol-specific, not generic. Avoid a generic `protocol_to_run(...)` name in public samples because it
hides the protocol-specific contract behind a second abstraction.

Protocol packages should consider these helper families. Not every protocol needs every helper, but when a protocol has
the concept the naming should stay consistent:

| Helper family | Shape | Purpose |
| --- | --- | --- |
| Run conversion | `<protocol>_to_run(...)` | Convert one protocol-native call/update/request into `Agent.run` or `Workflow.run` values. |
| Final rendering | `<protocol>_from_run(...)` | Convert a final `AgentResponse` / workflow result into protocol-native response payloads or operations. |
| Stream rendering | `<protocol>_stream_from_run(...)` | Convert `ResponseStream` / workflow updates into protocol-native events or operations. |
| Session id extraction | `<protocol>_session_id(...)` | Extract the protocol's natural continuation/partition key from the call, if present. |
| Command/action parsing | `<protocol>_command(...)` | Parse a protocol-native command/action/operation name without deciding app policy. |

Examples:

- `responses_to_run(...)`, `responses_from_run(...)`, `responses_stream_from_run(...)`,
  `responses_session_id(...)`;
- `telegram_to_run(...)`, `telegram_from_run(...)`, `telegram_stream_from_run(...)`,
  `telegram_session_id(...)`, `telegram_command(...)`;
- `activity_to_run(...)`, `activity_from_run(...)`, `activity_session_id(...)`, `activity_command(...)`;
- `discord_to_run(...)`, `discord_from_run(...)`, `discord_session_id(...)`, `discord_command(...)`.

The app still owns what a parsed command means. For example, a Telegram `/new`, Discord slash command, Bot Framework
command activity, or A2A cancellation/request action may parse through a command/action helper, but the route or SDK
handler decides whether that command clears a session, cancels a task, calls an agent, or is ignored.

Additional helper functions can be protocol-specific when the concept is not broadly shared. Examples include
`telegram_chat_id(...)`, `telegram_callback_query_id(...)`, `telegram_media_file_id(...)`,
`discord_interaction_id(...)`, `a2a_task_id(...)`, `a2a_context_id(...)`, and MCP tool/prompt/resource helpers. These
helpers should still stay side-effect-free: they extract, normalize, or describe protocol data, while app/native SDK code
performs acknowledgements, sends/edits messages, resolves protected file URLs, applies rate limits, and registers
handlers.

### Session continuity

Session continuity remains explicit. Run parsing and isolation/session id selection are separate operations because
isolation can come from more than one source:

- protocol input, such as OpenAI Responses `previous_response_id`, a Telegram chat id, or an Activity conversation id;
- running environment, such as Foundry Hosted Agents user/chat isolation context;
- app-specific trusted middleware or route state.

The app chooses which helper to call for that route and deployment. For example:

- `responses_session_id(body)` from `agent-framework-hosting-responses`, which can return either a `resp_*` previous
  response id or a `conv_*` conversation id when present;
- `telegram_session_id(update)` from `agent-framework-hosting-telegram`, which can choose the chat, user, thread, or
  other Telegram-native partitioning logic for that helper;
- `activity_session_id(activity)`, `discord_session_id(interaction_or_message)`, or
  `a2a_session_id(request_context)` from their respective protocol packages;
- `foundry_user_isolation_key()` or `foundry_chat_isolation_key()` from `agent-framework-foundry-hosting`.

Keep these helpers outside `responses_to_run(...)`, `telegram_to_run(...)`, and other run-input parsers. That makes the
trust boundary visible: using a request-derived key is a different decision than using a platform-provided isolation key.
Platform-provided isolation helpers must fail closed outside their trusted hosting environment. For example,
Foundry-specific helpers may read values established by Foundry hosting middleware, but must not treat raw request
headers as trusted Foundry isolation when the app is running outside Foundry. Implementations must test that non-Foundry
requests do not accept spoofable isolation headers as platform-provided keys.

A `SessionStore` stores `session_id -> AgentSession`, but it does not create sessions. `AgentState` resolves the agent
target and creates the session on first use:

For agent targets:

```python
session = await state.get_or_create_session(session_id)
target = await state.get_target()
result = await target.run(messages, session=session, options=options)
```

If the protocol mints a new continuation id as part of the response being created (for example, OpenAI Responses
`resp_*` ids), store the **post-run** session explicitly under that new id:

```python
session = await state.get_or_create_session(previous_response_id)
target = await state.get_target()
result = await target.run(messages, session=session, options=options)
await state.set_session(response_id, session)
```

`agent.run(...)` may update the session object (for example, with service continuation state), so the explicit store call
belongs after the run, not before it.

The session id is a partition key, not proof of identity. App or platform code must authenticate and authorize any
externally supplied key before using it.

### Workflow checkpoints

Workflow checkpointing is execution state, not protocol state. `WorkflowState` pairs a workflow target with checkpoint
state, but durable stores should not persist live `CheckpointStorage` client instances by value. Two shapes are useful:

- local/in-memory state may map `session_id -> CheckpointStorage` when the storage object is process-local;
- durable or multi-replica state should map `session_id -> checkpoint_id` (or an equivalent cursor/config) and use a
  workflow-owned or app-owned `CheckpointStorage` to load that checkpoint.

Workflow runs do not currently emit a checkpoint id on `WorkflowRunResult` or normal workflow events by default. The
runner receives checkpoint ids internally from `CheckpointStorage.save(...)`. App/state code that owns the storage can
observe the latest id by querying the storage after a run, for example
`await storage.get_latest(workflow_name=target.name)`.

For workflow targets, app code adapts the protocol helper output into the workflow's expected input and invokes the
workflow through the state object's target:

```python
storage = await state.get_or_create_checkpoint_storage(session_id)
target = await state.get_target()
result = await target.run(message=workflow_input, checkpoint_storage=storage)
latest = await storage.get_latest(workflow_name=target.name)
if latest is not None:
    await state.set_checkpoint_id(session_id, latest.checkpoint_id)
```

If a route wants to resume from a prior checkpoint, it explicitly chooses the checkpoint and passes it to
`workflow.run(...)`:

```python
storage = await state.get_or_create_checkpoint_storage(session_id)
target = await state.get_target()
checkpoint_id = await state.get_checkpoint_id(session_id)
if checkpoint_id is None:
    result = await target.run(message=workflow_input, checkpoint_storage=storage)
else:
    result = await target.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)
latest = await storage.get_latest(workflow_name=target.name)
if latest is not None:
    await state.set_checkpoint_id(session_id, latest.checkpoint_id)
```

`workflow.run(...)` writes checkpoints to the provided storage, so storage selection must be explicit at the route layer.
Protocol helper packages should not own checkpoint layout, route lifecycle, or durable execution.

## Non-goals for v1

The following remain outside the v1 contract:

- cross-channel identity linking (`IdentityLinker`, `local_identity_link`, or `agent-framework-hosting-entra`);
- identity allowlists or authorization policy (`IdentityAllowlist`, `AuthPolicy`);
- response routing beyond the originating protocol (`ResponseTarget`, active channel, specific linked channel,
  `all_linked`);
- push or payload codecs (`ChannelPush`, `ChannelPushCodec`);
- background/continuation delivery;
- durable task runners (`DurableTaskRunner`, `InProcessTaskRunner`);
- retry/replay policy (`RetryPolicy`);
- fan-out, multicast, or all-linked delivery;
- confidentiality tiers and `LinkPolicy`;
- a host-level multi-agent router.

These areas are follow-up enhancements covered by [ADR-0028](0028-hosting-linking-multicast-enhancements.md). They are
not prerequisites for shipping or using the v1 protocol-helper surface. ADR-0028 was written against the earlier
host/channel framing and must be revised to align with this protocol-helper and execution-state boundary before those
enhancements are implemented.

## Consequences

Positive:

- The released surface is smaller and easier to inspect: helpers plus state, not a channel framework.
- Protocol helpers can be used from FastAPI, Starlette, Azure Functions, Django, CLI tools, tests, or native SDK webhook
  handlers.
- App authors can use the authentication, dependency injection, lifecycle, and background-task tools they already know.
- Session continuity stays explicit and debuggable.
- Workflow checkpointing can still be centralized if needed without making protocol packages own routing.

Negative:

- Multi-protocol samples include explicit route/client code.
- Apps that want a batteries-included ASGI app must write or depend on an app-specific wrapper.
- Existing unreleased code and docs that mention channels, contribution, or hooks must be revised before release.

## More Information

- Follow-up linking and multicast ADR: [ADR-0028](0028-hosting-linking-multicast-enhancements.md). That ADR still uses
  some earlier host/channel terminology and must be aligned before implementation work starts.

## Appendix: Developer experience sketch

### Optional execution state

`AgentState` and `WorkflowState` stay small: they are target-specific state holders, not app hosts.

```python
from typing import Protocol

from agent_framework import AgentSession, CheckpointStorage, SupportsAgentRun, Workflow


class SupportsBuild(Protocol):
    def build(self) -> Workflow: ...


class SessionStore:
    async def get(self, session_id: str) -> AgentSession | None: ...
    async def set(self, session_id: str, session: AgentSession) -> None: ...
    async def delete(self, session_id: str) -> None: ...


class CheckpointStore:
    async def get(self, session_id: str) -> str | None: ...
    async def set(self, session_id: str, checkpoint_id: str) -> None: ...
    async def delete(self, session_id: str) -> None: ...


class AgentState:
    def __init__(self, target: SupportsAgentRun, *, session_store: SessionStore | None = None) -> None: ...
    async def get_target(self) -> SupportsAgentRun: ...
    async def get_or_create_session(self, session_id: str) -> AgentSession: ...
    async def set_session(self, session_id: str, session: AgentSession) -> None: ...


class WorkflowState:
    def __init__(
        self,
        target: Workflow | SupportsBuild,
        *,
        checkpoint_storage: CheckpointStorage | None = None,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None: ...
    async def get_target(self) -> Workflow: ...
    async def get_or_create_checkpoint_storage(self, session_id: str) -> CheckpointStorage: ...
    async def get_checkpoint_id(self, session_id: str) -> str | None: ...
    async def set_checkpoint_id(self, session_id: str, checkpoint_id: str) -> None: ...
```

`WorkflowState` accepts direct `Workflow` instances, workflow factories, and builder-shaped objects with
`build() -> Workflow`. That structurally covers `WorkflowBuilder` and the builders in `agent_framework_orchestrations`
without making `agent-framework-hosting` depend on the orchestration package.

### Responses-only route

This sketch shows the intended Responses-only shape. The protocol package owns the Agent Framework run conversion helpers and
response-id minting details; the application owns FastAPI routing, auth, policy adjustment, and response construction.

```python
import os

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentState  # pyright: ignore[reportAttributeAccessIssue]
from agent_framework_hosting_responses import create_response_id, responses_from_run, responses_session_id, responses_to_run  # pyright: ignore[reportAttributeAccessIssue]
from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse


app = FastAPI()
agent = Agent(
    client=OpenAIChatClient(),
    name="Assistant",
    instructions="Be concise and helpful.",
)
state = AgentState(agent)


@app.post("/responses")
async def responses(body: dict = Body(...), x_api_key: str | None = Header(default=None)) -> JSONResponse:
    if x_api_key != os.environ["RESPONSES_API_KEY"]:
        raise HTTPException(status_code=401, detail="bad api key")

    # parse the request body into a set of AF objects
    run = responses_to_run(body)
    # get the session id from the body
    # can be a resp_* for previous_response_id or a conv_* for a conversation
    session_id = responses_session_id(body)
    # create a new response_id for this run
    response_id = create_response_id()

    # in this space, the developer can make any adjustments to the request, i.e.:
    run["options"]["store"] = False
    run["options"].pop("model", None)

    # load the session (or create a new one) - this is optional
    # verify this caller owns session_id before loading it; API-key auth alone
    # does not prove ownership of a caller-supplied resp_* or conv_* id
    session = await state.get_or_create_session(session_id or response_id)
    # call the agent
    target = await state.get_target()
    result = await target.run(
        run["messages"],
        session=session,
        options=run["options"],
    )
    # agent.run may update the session, so store the post-run session explicitly under the response id
    # this might also be skipped, if the app chooses to respect `store=False` policy
    await state.set_session(response_id, session)
    return JSONResponse(responses_from_run(result, response_id=response_id, session_id=session_id))

```

### Responses-only Django class-based view

The same helper surface can be used without FastAPI. A Django app owns URL routing, CSRF/auth policy, request parsing,
and `JsonResponse` construction. In a real Django project this would live in the app's normal view module (for example
`assistant/views.py`) and be routed from that app's `urls.py`; Django discovers it through its standard project/app
layout, not through Agent Framework.

```python
import json
import os

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentState  # pyright: ignore[reportAttributeAccessIssue]
from agent_framework_hosting_responses import create_response_id, responses_from_run, responses_session_id, responses_to_run  # pyright: ignore[reportAttributeAccessIssue]
from django.http import HttpRequest, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.views import View


agent = Agent(
    client=OpenAIChatClient(),
    name="Assistant",
    instructions="Be concise and helpful.",
)
state = AgentState(agent)


class ResponsesView(View):
    async def post(self, request: HttpRequest) -> JsonResponse:
        if request.headers.get("x-api-key") != os.environ["RESPONSES_API_KEY"]:
            return HttpResponseForbidden("bad api key")

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponseBadRequest("invalid json")

        run = responses_to_run(body)
        session_id = responses_session_id(body)
        response_id = create_response_id()
        options = run["options"]
        # verify this caller owns session_id before loading it; API-key auth alone
        # does not prove ownership of a caller-supplied resp_* or conv_* id
        session = await state.get_or_create_session(session_id or response_id)
        target = await state.get_target()
        result = await target.run(
            run["messages"],
            session=session,
            options=options,
        )
        await state.set_session(response_id, session)
        return JsonResponse(responses_from_run(result, response_id=response_id, session_id=session_id))
```
