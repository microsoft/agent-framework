# agent-framework-hosting-responses

OpenAI Responses-shaped helpers for app-owned Agent Framework hosting.

This package provides the Responses-specific conversion layer:

- `responses_to_run(...)` — convert a Responses request body into Agent
  Framework run values.
- `responses_session_id(...)` — return `(session_id, is_conversation_id)` for a
  prior `resp_*` response id or the `conv_*` id from the official `conversation`
  field, or `(None, None)` when neither is present.
- `create_conversation_id(...)` — mint a Responses-shaped conversation id.
- `create_response_id(...)` — mint a Responses-shaped response id.
- `responses_from_run(...)` — convert an `AgentResponse` into a
  Responses-compatible JSON payload.
- `responses_from_streaming_run(...)` — convert an Agent Framework
  `ResponseStream` into Responses-compatible SSE events.

Responses refusal parts round-trip as text carrying
`additional_properties["model_output_kind"] == "refusal"` and native
`response.refusal.*` events. Streaming text and refusal output includes the
standard output-item and content-part lifecycle with stable item IDs, indexes,
and sequence numbers.

Final streaming events match the rendered response status:
`response.completed`, `response.incomplete`, or `response.failed`. Finalizing a
stream with a nonterminal status produces `response.failed`. Response status is
read from the raw transport representation rather than free-form agent metadata,
and failed transport responses preserve their structured error. A valid native
Responses usage object is preserved before considering Agent Framework counters;
the two sources are never merged. Otherwise, counters map only from matching
Agent Framework fields and the installed OpenAI SDK schema validates the shape.
Missing counters never borrow from another field or become invented zeros; an
absent total alone is derived from known input and output counts. Usage that
cannot form a consistent Responses shape is omitted.

FastAPI/Starlette/Django/Azure Functions code owns route registration,
authentication, status codes, response construction, and background work.

```python
from agent_framework_hosting import AgentState
from agent_framework_hosting_responses import (
    create_response_id,
    responses_from_run,
    responses_session_id,
    responses_to_run,
)
from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()
state = AgentState(agent)


@app.post("/responses")
async def responses(body: dict = Body(...)) -> JSONResponse:
    run = responses_to_run(body)
    session_id, is_conversation_id = responses_session_id(body)
    response_id = create_response_id()
    session = await state.get_or_create_session(session_id or response_id)
    result = await (await state.get_target()).run(
        run["messages"],
        session=session,
        options=run["options"],
    )
    if is_conversation_id:
        # The app must serialize writers that advance this stable id.
        await state.set_session(session_id, session)
    else:
        await state.set_session(response_id, session)
    conversation_id = session_id if is_conversation_id else None
    return JSONResponse(responses_from_run(result, response_id=response_id, conversation_id=conversation_id))
```

`previous_response_id` identifies an immutable continuation snapshot: multiple
requests may branch from it and store their results under distinct new response
ids. `conversation` accepts either a conversation id string or an `{"id": ...}`
object and identifies a mutable head; only one caller should advance it at a
time. Supplying both mechanisms is invalid.

The former `conversation_id` request field remains available only as a
deprecated fallback when neither standard mechanism is present. These helpers
do not provide per-conversation locking.

`AgentState` lives in
[`agent-framework-hosting`](https://pypi.org/project/agent-framework-hosting/).
The experimental in-memory and file-backed session stores live in core as
`agent_framework.SessionStore` and `agent_framework.FileSessionStore`.
