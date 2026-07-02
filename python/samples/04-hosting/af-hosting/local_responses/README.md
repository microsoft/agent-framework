# local_responses — Responses helpers with native FastAPI routes

The smallest end-to-end Responses hosting shape: one Foundry agent with a
`@tool`, one native FastAPI route, a small `SessionStore`, and the Responses
helper functions:

- `responses_to_run(...)`
- `responses_session_id(...)`
- `create_response_id(...)`
- `responses_from_run(...)`

The sample demonstrates the lighter hosting direction. Agent Framework provides
the run conversion and session-state pieces; FastAPI owns route registration,
request bodies, response objects, and server startup.

What the route demonstrates:

- **Strips** caller-supplied `model` / `temperature` / `store` so the app owns
  deployment and persistence settings.
- **Forces** a `reasoning` preset (`effort=medium`, `summary=auto`) on every
  turn.
- Produces the AF messages, options, and session id that the route passes to
  `agent.run(...)`.

`app:app` is a module-level FastAPI ASGI app; recommended local launch is
Hypercorn.

## Run

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export FOUNDRY_MODEL=gpt-5-nano
az login

uv sync
uv run hypercorn app:app --bind 0.0.0.0:8000
```

Single-process for quick iteration:

```bash
uv run python app.py
```

## Call locally

```bash
uv sync --group dev

# Plain OpenAI SDK call:
uv run python call_server.py

# The client intentionally omits `model`; the app chooses the backing deployment
# from FOUNDRY_MODEL.

# The script then sends a second turn, "And what about Amsterdam?", using the
# first `response.id` as `previous_response_id`.

# Same two-turn interaction through an Agent Framework Agent backed by
# OpenAIChatClient:
uv run python call_server_af.py
```

> This sample is **local-only** — no Dockerfile, no Foundry packaging.
