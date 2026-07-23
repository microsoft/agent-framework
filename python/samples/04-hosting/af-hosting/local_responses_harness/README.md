# local_responses_harness — hosting a harness agent behind Responses routes

The sibling of [`local_responses/`](../local_responses), with one change: the
hosted target is a batteries-included **harness agent** built with
[`create_harness_agent`](../../../02-agents/harness/README.md) instead of a plain
`Agent`.

Everything else is the same helper-first Responses hosting shape: one native
FastAPI route, a small `SessionStore` via `AgentState`, and the Responses helper
functions:

- `responses_to_run(...)`
- `responses_session_id(...)`
- `create_response_id(...)`
- `responses_from_run(...)`
- `responses_from_streaming_run(...)`

The takeaway is that a harness agent is just an `Agent`, so it drops straight
into the same `AgentState` / Responses-helper seam as any other target. The
harness supplies the function-invocation loop, per-service-call history
persistence, context-window compaction, todo management, and heuristic tool
approval on top of a single `@tool`.

What the sample does with the harness:

- Turns off the interactive-only features (plan/execute mode and the Textual
  console) because a one-shot HTTP request has no console to drive.
- Turns off web search to keep the sample self-contained.
- Keeps todo management and compaction enabled, so the target is a genuine
  harness agent and not just a relabelled plain `Agent`.
- Registers `lookup_weather` with `approval_mode="never_require"` so a headless
  run never blocks waiting for a human to approve a tool call.

What the route demonstrates (identical to `local_responses/`):

- Uses an explicit request-option allowlist. This sample only allows
  `max_tokens` and `reasoning`; all other caller-supplied options, including
  `model`, `temperature`, `store`, `tools`, and `tool_choice`, are denied by
  default. Your app decides the exact allowed, altered, and denied options.
- Produces the AF messages, options, and session id that the route passes to
  `agent.run(...)`.
- **Stores** each newly minted response id for the session it was just resolved
  from, via `state.set_session(response_id, session)` after `agent.run(...)` has
  updated the session. OpenAI's `previous_response_id` rotates every turn *by
  design* — it lets a caller continue from any earlier response, not just the
  latest one — so every response id needs to stay independently resolvable.
- Treats an unknown `conversation_id` as a request to create a new local
  session. Your app can choose a stricter policy.

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
```

The client intentionally omits `model`; the app chooses the backing deployment
from `FOUNDRY_MODEL`. The script then sends two more turns, each continuing from
the previous turn's `response.id` as `previous_response_id`. The third turn asks
about the first turn's city, so it only succeeds if the harness agent behind the
route still remembers that far back in the chain.

> This sample is **local-only** — no Dockerfile, no Foundry packaging.
