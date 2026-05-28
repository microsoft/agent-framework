# local_responses_workflow — workflow target with structured intake + checkpoints

A `Workflow` (intake → writer → legal reviewer → formatter) hosted
behind **both the Responses API and the Invocations API**, with the
host configured to **persist per-conversation checkpoints**. Mirrors
[`../../foundry-hosted-agents/responses/04_workflows/`](../../foundry-hosted-agents/responses/04_workflows/)
but uses the `agent-framework-hosting` stack instead of the
Foundry-Hosted-Agents runtime, and adds a structured intake step
(`SloganBrief` with `topic` / `style` / `audience` fields) at the front
of the workflow.

## What's interesting

- `AgentFrameworkHost(target=workflow, …)` — the host detects a
  `Workflow` target and dispatches to `workflow.run(...)` (no
  `Agent.create_session(...)`).
- Two channels are mounted side-by-side (`ResponsesChannel` at
  `/responses`, `InvocationsChannel` at `/invocations/invoke`). Both
  share the **same `brief_hook`** that **adapts the channel-native
  input into the workflow start executor's typed input** — Responses
  delivers a `list[Message]`, Invocations delivers a `str`, but the
  hook normalises both to text and produces a `SloganBrief`.
- The hook parses the inbound text as JSON
  (`{"topic": ..., "style": ..., "audience": ...}`); if parsing fails
  it uses the whole text as `topic` with defaults.
- The workflow's first executor (`BriefIntakeExecutor`) accepts
  `SloganBrief` directly — that's what gets sent into `workflow.run(...)`
  by the host.
- `checkpoint_location=storage/checkpoints/` — the host scopes a
  `FileCheckpointStorage` per conversation (Responses keys it on
  `previous_response_id` / `conversation_id`; Invocations keys it on
  `session_id`) and **restores from the latest checkpoint at the start
  of every turn** before applying the new input. Without an isolation
  key the host skips checkpointing for that request.
- No `HistoryProvider` — the workflow owns its own state via the
  checkpoint store.

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

Two clients are provided next to `app.py`:

- **`call_server.py`** — Python client using the OpenAI SDK (Responses
  API only).
- **`call_server.rest`** — raw REST examples for **both** the Responses
  and Invocations endpoints (open in VS Code with the REST Client
  extension or any compatible HTTP-file runner).

```bash
uv sync --group dev

# Structured brief via the OpenAI SDK (Responses API):
uv run python call_server.py \
    '{"topic": "electric SUV", "style": "playful", "audience": "young families"}'

# Plain topic (style/audience default to "modern" / "general"):
uv run python call_server.py "electric SUV"

# Continue an existing conversation by its `response.id`:
uv run python call_server.py --previous-response-id <response-id> \
    '{"topic": "electric SUV", "style": "retro", "audience": "boomers"}'
```

After a few turns, inspect `storage/checkpoints/<isolation_key>/` —
each conversation has its own subdirectory of checkpoint files written
by the host.

> This sample is **local-only** — no Dockerfile, no Foundry packaging.
> For a Foundry-Hosted-Agents-compatible packaging see
> [`../foundry_hosted_agent`](../foundry_hosted_agent).
