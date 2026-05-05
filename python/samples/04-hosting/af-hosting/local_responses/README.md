# local_responses — Responses-only with a settings-altering hook

The smallest end-to-end `agent-framework-hosting` shape: one Foundry
agent with a `@tool`, one `ResponsesChannel`, one `run_hook`. Useful as
the entry-point sample for understanding the **channel run-hook** seam
without any multi-channel or identity-link concerns.

What the run hook demonstrates:

- **Strips** caller-supplied `temperature` / `store` so the host owns
  those settings.
- **Forces** a `reasoning` preset (`effort=medium`, `summary=auto`) on
  every turn — caller-side overrides are ignored.

`app:app` is a module-level Starlette ASGI app; recommended local launch
is Hypercorn.

## Run

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export FOUNDRY_MODEL=gpt-5.4-nano
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

# Plain call:
uv run python call_server.py "What is the weather in Tokyo?"

# Continue an existing conversation by its `response.id`:
uv run python call_server.py --previous-response-id <response-id> "And in Seattle?"
```

> This sample is **local-only** — no Dockerfile, no Foundry packaging.
> For a Foundry-Hosted-Agents-compatible packaging see
> [`../foundry_hosted_agent`](../foundry_hosted_agent).
