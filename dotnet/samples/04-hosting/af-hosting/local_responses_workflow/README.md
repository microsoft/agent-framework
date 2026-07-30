# Hosting Responses Workflow (client / server)

A client/server pair showing how to expose a **workflow** over the OpenAI Responses protocol from an
ASP.NET Core route you write, with per-session checkpoint resume, and how to consume it from .NET two
different ways.

```
local_responses_workflow/
├── Server/   # exposes POST /responses; previous_response_id continuation with checkpoint resume
└── Client/   # consumes it two ways: CC (IChatClient) and MAF (AIAgent)
```

## Server

The server owns routing, authentication, and checkpoint storage. It uses the `OpenAIResponses` conversion
helpers for the wire protocol and `HostedWorkflowState` for per-session checkpoint resume. The workflow is a
brief adapter, a slogan-writer agent, and a formatter that renders one slogan line. The first turn runs the
workflow forward; later turns restore the latest checkpoint and run forward with the new brief. It binds to
`http://localhost:5001`.

The server supports **`previous_response_id` continuation only** and **rejects `conversation` continuity
with HTTP 400**. Because `previous_response_id` rotates every turn, the app owns a cursor that maps each
response id to the stable workflow session id, so the whole rotating chain resumes the same checkpointed
run.

See [Server/README.md](Server/README.md).

## Client

A single program that runs the same two-turn conversation twice, once per consumption path:

- **CC** — a plain `Microsoft.Extensions.AI.IChatClient` (the lower-level chat-client path).
- **MAF** — a Microsoft Agent Framework `AIAgent` + `AgentSession` (the higher-level agent path).

Both send a JSON brief on the first turn and a refinement on the second, following the rotating
`previous_response_id` chain (the CC path threads it by hand; the MAF path lets `AgentSession` do it). The
follow-up only makes sense if the workflow resumed the first turn's checkpoint.

See [Client/README.md](Client/README.md).

## Run

Start the server in one shell:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<your-resource>.services.ai.azure.com/api/projects/<your-project>"
export FOUNDRY_MODEL="gpt-5.4-mini"   # optional, defaults to gpt-5.4-mini
dotnet run --project Server
```

Then run the client in another shell:

```bash
dotnet run --project Client
```

The client defaults to `http://localhost:5001`; override with `RESPONSES_SERVER_URL`.

## Why previous_response_id needs a cursor

`previous_response_id` changes every turn, so it cannot key checkpoint storage directly. The app maps each
response id to the stable workflow session id, so every id in the rotating chain resumes the same
checkpointed run. Sending `conversation` is rejected with HTTP 400 to keep this sample focused on one
continuation mode.