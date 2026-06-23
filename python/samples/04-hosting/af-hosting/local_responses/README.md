# local_responses — Responses-only with a settings-altering hook

The smallest end-to-end `agent-framework-hosting` shape: one Foundry
agent with a `@tool`, one `ResponsesChannel`, one `run_hook`. Useful as
the entry-point sample for understanding the **channel run-hook** seam
without any multi-channel or identity-link concerns.

What the run hook demonstrates:

- **Strips** caller-supplied `model` / `temperature` / `store` so the
  host owns the backing deployment and persistence settings.
- **Forces** a `reasoning` preset (`effort=medium`, `summary=auto`) on
  every turn — caller-side overrides are ignored.

`app:app` is a module-level Starlette ASGI app; recommended local launch
is Hypercorn.

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

# The client intentionally omits `model`; the host chooses the backing
# deployment from FOUNDRY_MODEL.

# The script then sends a second turn, "And what about Amsterdam?",
# using the first `response.id` as `previous_response_id`.

# Same two-turn interaction through an Agent Framework Agent backed by
# OpenAIChatClient, with streaming enabled:
uv run python call_server_af.py
```

> This sample is **local-only** — no Dockerfile, no Foundry packaging.
