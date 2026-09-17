# Server (Hosting Responses Workflow)

Server half of the [Hosting Responses Workflow](../README.md) sample.

Exposes a workflow over the OpenAI Responses protocol on a `POST /responses` route you write. The workflow
is a brief adapter, a slogan-writer agent, and a formatter that renders one slogan line. It uses the
`OpenAIResponses` conversion helpers for the wire protocol and `HostedWorkflowState` for per-session
checkpoint resume.

This server supports **`previous_response_id` continuation only** and **rejects `conversation` continuity
with HTTP 400**. Because `previous_response_id` rotates every turn, the app owns a cursor that maps each
response id to the stable workflow session id, so the whole rotating chain resumes the same checkpointed
run. The first turn runs the workflow forward; later turns restore the latest checkpoint and run forward
with the new brief. Binds to `http://localhost:5001` (override with `ASPNETCORE_URLS`).

`HostedWorkflowState` is constructed with a **workflow factory** and `cacheWorkflow: false` (the default,
shown explicitly), so it builds a fresh workflow instance for every run. This lets independent sessions run
concurrently — a single shared `Workflow` instance permits only one active run, so the instance constructor
cannot process turns concurrently. A resume rehydrates a fresh instance from the session's checkpoint in the
shared `CheckpointManager`, so per-run instances still continue the same run. (Passing `cacheWorkflow: true`
would instead build the workflow once, lazily, and reuse it — a deferred, cached target that, like a shared
instance, cannot run concurrent turns.) Concurrent turns against the *same* session id are the application's
responsibility; a production app owns that per-session single-writer coordination.

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<your-resource>.services.ai.azure.com/api/projects/<your-project>"
export FOUNDRY_MODEL="gpt-5.4-mini"
dotnet run
```

Call it directly, following the response-id chain across turns (the second call continues the first):

```bash
curl -s http://localhost:5001/responses -H "content-type: application/json" \
  -d '{ "input": "{\"topic\": \"electric SUV\", \"style\": \"playful\", \"audience\": \"young families\"}" }'

# Take the "id" (resp_...) from the response above and pass it as previous_response_id:
curl -s http://localhost:5001/responses -H "content-type: application/json" \
  -d '{ "input": "Make it a little more premium.", "previous_response_id": "resp_..." }'
```