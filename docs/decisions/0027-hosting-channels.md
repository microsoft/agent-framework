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
- Keep stateful execution support explicit: session lookup, session reset, and workflow checkpointing may still need a
  small AF-owned home.
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
- Good: a small state object can still own target-coupled state such as an agent/workflow target, a `SessionStore`, and
  future workflow checkpoint coordination.
- Good: provides maximum configurability in handling input and outputs (outside of the conversions)
- Bad: building a first iteration of a new Host is more verbose.
- Bad: samples show more explicit route/client code than a fully assembled channel host.

## Decision Outcome

Chosen option: **protocol helpers plus optional execution state**.

Protocol packages own:

- parsing protocol-native input into Agent Framework run input and options;
- rendering `AgentResponse`, `AgentResponseUpdate`, workflow results, or workflow updates back into protocol-native
  response/event payloads;
- protocol-specific isolation/session id helper functions when useful, such as `telegram_chat_session_id(update)`;
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

`AgentFrameworkState`, if provided, is limited to shared execution state:

- one first-class hostable target: either a `SupportsAgentRun` agent-compatible object or a `Workflow`;
- a `SessionStore` instance or factory;
- optional workflow checkpoint execution state.

It is **not** an app object, channel registry, or route owner. It does not own FastAPI/Starlette setup, route
contribution, protocol dispatch, command projection, or native SDK calls.

### Helper naming

Helpers should be protocol-specific, not generic. Prefer:

- `responses_to_run(...)`
- `responses_from_run(...)`
- `responses_stream_event_from_run(...)` if streaming needs a separate event helper
- `telegram_to_run(...)`
- `telegram_from_run(...)`

Avoid a generic `protocol_to_run(...)` name in public samples because it hides the protocol-specific contract behind a
second abstraction.

### Session continuity

Session continuity remains explicit. Run parsing and isolation/session id selection are separate operations because
isolation can come from more than one source:

- protocol input, such as OpenAI Responses `previous_response_id`, a Telegram chat id, or an Activity conversation id;
- running environment, such as Foundry Hosted Agents user/chat isolation context;
- app-specific trusted middleware or route state.

The app chooses which helper to call for that route and deployment. For example:

- `responses_session_id(body)` from `agent-framework-hosting-responses`, which can return either a `resp_*` previous
  response id or a `conv_*` conversation id when present;
- `telegram_chat_session_id(update)` from `agent-framework-hosting-telegram`;
- `foundry_user_isolation_key()` or `foundry_chat_isolation_key()` from `agent-framework-foundry-hosting`.

Keep these helpers outside `responses_to_run(...)`, `telegram_to_run(...)`, and other run-input parsers. That makes the
trust boundary visible: using a request-derived key is a different decision than using a platform-provided isolation key.

A `SessionStore` resolves that key into an `AgentSession`:

For agent targets:

```python
session = await state.session_store.get(session_id)
result = await state.target.run(messages, session=session, options=options)
```

For workflow targets, app code adapts the protocol helper output into the workflow's expected input and invokes the
workflow through the state object's target:

```python
result = await state.target.run(message=workflow_input)
```

`SessionStore.reset(session_id)` rotates or clears the current session for non-persisted servers. Persisted stores can
implement the same async interface later.

The session id is a partition key, not proof of identity. App or platform code must authenticate and authorize any
externally supplied key before using it.

### Workflow checkpoints

Workflow checkpointing is execution state, not protocol state. A small state object may help coordinate checkpoint
storage for workflow targets, but protocol helper packages should not own checkpoint layout, route lifecycle, or durable
execution.

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

## Validation Gates

Before this ADR is considered implemented:

- A Responses sample uses normal FastAPI route code plus `responses_to_run(...)`, `responses_from_run(...)`, and
  `SessionStore`; it does not use `ResponsesChannel` or `ChannelRunHook`.
- Protocol helper tests cover Responses input parsing, option policy, response rendering, and streaming event rendering.
- Protocol helper tests cover Telegram message parsing, typing events, streaming update events, final response rendering,
  and session-key derivation.
- `SessionStore` tests prove session reuse and reset behavior.
- The same helper functions can be used without FastAPI in at least one direct unit test or sample.
- The v1 public package docs do not advertise `Channel`, contribution, command, or hook APIs as the intended released
  surface.
- The Python spec is updated to match this revised contract.

## More Information

- Follow-up linking and multicast ADR: [ADR-0028](0028-hosting-linking-multicast-enhancements.md). That ADR still uses
  some earlier host/channel terminology and must be aligned before implementation work starts.

## Appendix: Developer experience sketch

### Optional execution state

`AgentFrameworkState` stays small: it is only the target/session/checkpoint state holder. The target can be an agent or
a workflow. It is shown here for shape, but the Responses route below imports it from `agent_framework_hosting`.

```python
from agent_framework import SupportsAgentRun, Workflow


class AgentFrameworkState:
    def __init__(self, target: SupportsAgentRun | Workflow, *, session_store: SessionStore | type[SessionStore]) -> None:
        self.target = target
        self.session_store = session_store(target) if isinstance(session_store, type) else session_store
```

### Responses-only route

This sketch shows the intended Responses-only shape. The protocol package owns the Agent Framework run conversion helpers and
response-id minting details; the application owns FastAPI routing, auth, policy adjustment, and response construction.

```python
import os

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentFrameworkState, SessionStore
from agent_framework_hosting_responses import (
    create_response_id,
    responses_from_run,
    responses_session_id,
    responses_to_run,
)
from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse


app = FastAPI()
agent = Agent(
    client=OpenAIChatClient(),
    name="Assistant",
    instructions="Be concise and helpful.",
)
state = AgentFrameworkState(agent, session_store=SessionStore)


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
    options = dict(run["options"])
    options["store"] = False
    options.pop("model", None)

    # load the session (or a new one)
    session = await state.session_store.get(session_id or response_id)
    # call the agent
    result = await state.target.run(
        run["messages"],
        session=session,
        options=options,
    )
    # any post-processing steps the developer wants to do can be done here
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
from agent_framework_hosting import AgentFrameworkState, SessionStore
from agent_framework_hosting_responses import (
    create_response_id,
    responses_from_run,
    responses_session_id,
    responses_to_run,
)
from asgiref.sync import async_to_sync
from django.http import HttpRequest, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.views import View


agent = Agent(
    client=OpenAIChatClient(),
    name="Assistant",
    instructions="Be concise and helpful.",
)
state = AgentFrameworkState(agent, session_store=SessionStore)


class ResponsesView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
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
        result = async_to_sync(state.target.run)(
            run["messages"],
            session=async_to_sync(state.session_store.get)(session_id or response_id),
            options=options,
        )
        return JsonResponse(responses_from_run(result, response_id=response_id, session_id=session_id))
```
