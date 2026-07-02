# agent-framework-hosting-responses

OpenAI Responses-shaped helpers for app-owned Agent Framework hosting.

This package provides the Responses-specific conversion layer:

- `responses_to_run(...)` — convert a Responses request body into Agent
  Framework run values.
- `responses_session_id(...)` — extract a prior `resp_*` response id or
  `conv_*` conversation id from the request body when present.
- `create_response_id(...)` — mint a Responses-shaped response id.
- `responses_from_run(...)` — convert an `AgentResponse` into a
  Responses-compatible JSON payload.
- `responses_stream_events_from_run(...)` — convert an Agent Framework
  `ResponseStream` into Responses-compatible SSE events.

FastAPI/Starlette/Django/Azure Functions code owns route registration,
authentication, status codes, response construction, and background work.

```python
from agent_framework_hosting import AgentFrameworkState, SessionStore
from agent_framework_hosting_responses import (
    create_response_id,
    responses_from_run,
    responses_session_id,
    responses_to_run,
)
from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()
state = AgentFrameworkState(agent, session_store=SessionStore)


@app.post("/responses")
async def responses(body: dict = Body(...)) -> JSONResponse:
    run = responses_to_run(body)
    session_id = responses_session_id(body)
    response_id = create_response_id()
    result = await (await state.get_target()).run(
        run["messages"],
        session=await state.get_session(session_id or response_id),
        options=run["options"],
    )
    return JSONResponse(responses_from_run(result, response_id=response_id, session_id=session_id))
```

The base execution-state helpers live in
[`agent-framework-hosting`](https://pypi.org/project/agent-framework-hosting/).
