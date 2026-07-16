# local_responses_workflow — Responses helpers with a workflow target

This sample shows the helper-first hosting shape for a local workflow:

- `responses_to_run(...)` parses the Responses request body.
- `WorkflowState` resolves the workflow target.
- FastAPI owns the route and response construction.
- The app owns file-based checkpoint storage and the
  `response_id -> checkpoint_id` cursor used to continue from a previous
  response.
- Continuation is intentionally limited to `previous_response_id`; this sample
  rejects `conversation_id` continuity with HTTP 400.

The workflow writes a slogan with one Foundry-backed writer agent and a small
deterministic formatter executor. That keeps the sample focused on native
FastAPI routing, Responses helpers, `WorkflowState`, and app-owned checkpoint
cursor storage. Both workflow checkpoints and the checkpoint cursor file are
stored under the sample's local `storage/` root. Checkpoints are scoped into
per-continuation buckets so a "latest checkpoint" lookup cannot cross
conversations.

## Production readiness

This is not a full-fledged production deployment. Before exposing this pattern
to callers, add authentication and authorization at the infrastructure layer,
the FastAPI app layer, or inside the route body.

Session continuation deserves particular care: treat `previous_response_id` as
an untrusted request value, authorize the caller before restoring or storing a
checkpoint cursor for that id, and partition durable checkpoint/cursor storage
by tenant/user as appropriate for your application.

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
uv run python call_server.py '{"topic": "electric SUV", "style": "playful", "audience": "young families"}'
```

The script sends a follow-up using the first response id as
`previous_response_id`, so the workflow restores the prior checkpoint before
running the next turn. It deliberately does not send `conversation_id`, because
this sample rejects `conversation_id` continuation.

> This sample uses local file storage under `storage/` for both workflow
> checkpoints and checkpoint cursors. The checkpoint bucket names are hashed
> from the continuation id before they are used as directory names. Replace this
> with production-grade durable storage for multi-replica or transient hosting.
