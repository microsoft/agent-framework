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
- **Stores** each newly minted response id for the session it was just
  resolved from, via `state.set_session(response_id, session)` after
  `agent.run(...)` has updated the session.
  OpenAI's `previous_response_id` rotates every turn *by design* — it lets a
  caller continue from any earlier response, not just the latest one — so
  every response id needs to stay independently resolvable, not just the
  most recent.

`app:app` is a module-level FastAPI ASGI app; recommended local launch is
Hypercorn.

## Production readiness

This is not a full-fledged production deployment. Before exposing this pattern
to callers, add authentication and authorization at the infrastructure layer,
the FastAPI app layer, or inside the route body.

Session continuation deserves particular care: treat `previous_response_id` and
`conversation_id` as untrusted request values, authorize the caller before
loading or storing a session for those ids, and partition any durable session
store by tenant/user as appropriate for your application.

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

# The script then sends two more turns, each continuing from the previous
# turn's `response.id` as `previous_response_id`. The third turn asks about
# the first turn's city, so it only succeeds if the server still remembers
# that far back in the chain.

# Same three-turn interaction through an Agent Framework Agent backed by
# OpenAIChatClient:
uv run python call_server_af.py
```

> This sample is **local-only** — no Dockerfile, no Foundry packaging.
