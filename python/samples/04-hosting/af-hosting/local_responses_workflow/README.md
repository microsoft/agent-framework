# local_responses_workflow — workflow target with run-hook prep + checkpoints

A `Workflow` (writer → legal reviewer → formatter) hosted
behind the **Responses API**, with the host configured to
**persist per-conversation checkpoints**. Mirrors
[`../../foundry-hosted-agents/responses/05_workflows/`](../../foundry-hosted-agents/responses/05_workflows/)
but uses the `agent-framework-hosting` stack instead of the
Foundry-Hosted-Agents runtime. The `run_hook` prepares the writer prompt
before the workflow starts.

## What's interesting

- `AgentFrameworkHost(target=workflow, …)` — the host detects a
  `Workflow` target and dispatches to `workflow.run(...)` (no
  `Agent.create_session(...)`).
- `ResponsesChannel` is mounted at `/responses` with a `prepare_writer_prompt`
  run hook that **adapts the channel-native input into the workflow start
  executor's input**. Responses delivers a `list[Message]`; the hook normalises
  it to text and prepares the prompt the writer agent receives.
- The hook parses the inbound text as JSON
  (`{"topic": ..., "style": ..., "audience": ...}`); if parsing fails
  it uses the whole text as `topic` with defaults.
- The workflow starts directly at the writer `AgentExecutor`; no extra intake
  executor is needed because the hook performs the one preparation step.
- `checkpoint_location=storage/checkpoints/` — the host scopes a
  `FileCheckpointStorage` per conversation (Responses keys it on
  `previous_response_id` / `conversation_id`) and **restores from the
  latest checkpoint at the start of every turn** before applying the new
  input. Without an isolation key the host skips checkpointing for that request.
- No `HistoryProvider` — the workflow owns its own state via the
  checkpoint store.

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

Two clients are provided next to `app.py`:

- **`call_server.py`** — Python client using the OpenAI SDK (Responses
  API only).
- **`call_server.rest`** — raw REST examples for the Responses endpoint
  (open in VS Code with the REST Client extension or any compatible HTTP-file
  runner).

```bash
uv sync --group dev

# Structured brief via the OpenAI SDK (Responses API):
uv run python call_server.py \
    '{"topic": "electric SUV", "style": "playful", "audience": "young families"}'

# The client intentionally omits `model`; the host chooses the backing
# deployment from FOUNDRY_MODEL.

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
> A Foundry-Hosted-Agents-compatible packaging sample will be added separately.
