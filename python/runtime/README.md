# Python Agent Runtime (POC) — Architecture Overview

A minimal, in-process actor runtime for hosting AI agents in Python. It mirrors the core patterns of the .NET Agent Framework: actor-per-conversation, message passing, and a small HTTP surface for invocation. This document focuses on architecture and how pieces fit together.

## Layers and files

- Runtime abstractions — `agent_runtime/runtime_abstractions.py`
  - Types: `ActorId`, `ActorMessage`, `ActorRequestMessage`, `ActorResponseMessage`, `RequestStatus`
  - Interfaces: `IActor`, `IActorRuntimeContext`, `IActorClient`, `ActorResponseHandle`, `IActorStateStorage`
- In‑process runtime — `agent_runtime/runtime.py`
  - `InMemoryStateStorage` (dev-only), `InProcessActorRuntime`, `InProcessActorContext`, `InProcessActorClient`
  - Request tracking with a final `Future` + progress `asyncio.Queue`
- Agent bridge — `agent_runtime/agent_actor.py`
  - `AgentActor`: wraps framework agents and executes them inside the actor loop
  - Sample agents for demos: `EchoAgent`, `MockAIAgent`
  - Note: Integration uses the framework’s concrete types from `python/packages/main` (no separate “AI agent” abstraction in the runtime)
- HTTP API — `agent_runtime/http_api.py`
  - FastAPI app with lifecycle management, agent registration, and a `POST /agents/{agent_name}/run` endpoint
  - Optional Azure OpenAI agent registration based on environment variables
- Examples — `runtime/examples/`
  - `example.py` (runtime + mock/echo agents), `framework_example.py` (direct framework integration)

Tip: There is also `agent_runtime/abstractions.py`, an earlier combined abstraction module. The core runtime uses `runtime_abstractions.py` for infrastructure concerns; prefer that when reading the actor model.

## Message flow and threading

High level sequence for an HTTP call:
1) Client calls `POST /agents/{agent_name}/run` with messages and optional `conversation_id`.
2) HTTP layer builds `ActorId(type_name=agent_name, instance_id=conversation_id or "http-{agent_name}")` and sends a request via `InProcessActorClient`.
3) Runtime resolves/creates an actor using a registered factory for `type_name`, starts it if needed, and enqueues the request on the actor’s inbox.
4) `AgentActor.run()` consumes messages sequentially (single-threaded per actor) via `context.watch_messages()`, calls the underlying framework agent, updates state, then completes the request.
5) The caller awaits the `ActorResponseHandle.get_response()`; streaming updates are supported at the runtime handle level but not exposed over HTTP in this POC.

Threading model:
- One `asyncio.Task` per actor instance; each actor processes messages sequentially from an `asyncio.Queue`.
- System-level concurrency via multiple actor tasks running in parallel.

State model:
- `IActorStateStorage` defines persistence; current implementation is `InMemoryStateStorage` only.
- `AgentActor` saves minimal, simplified thread metadata; full conversation serialization/restoration is not implemented yet.

Identity and registration:
- Register factories by type name (e.g., "echo", "mock-ai").
- The HTTP route segment `{agent_name}` maps to the actor `type_name`. The `conversation_id` becomes the actor `instance_id` for continuity.

## Current capabilities and gaps

- Actor model: complete for in-process, single-node usage.
- HTTP API: working, includes OpenAPI docs and health endpoint.
- State: in-memory only; persistence interfaces exist for future backends.
- Streaming: runtime scaffolding exists (`watch_updates`/progress), but HTTP does not stream yet.
- Observability: basic logging; no OpenTelemetry wiring.

## Run it locally (Windows PowerShell)

From this folder (`python/runtime`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Console demo:
```powershell
python .\examples\example.py
```

HTTP API:
```powershell
python -m agent_runtime.http_api
```

Test with curl (PowerShell ships with curl.exe):
```powershell
curl http://localhost:8000/agents

curl -X POST http://localhost:8000/agents/mock-ai/run `
  -H "Content-Type: application/json" `
  -d '{
    "agent_name": "mock-ai",
    "conversation_id": "test-conversation",
    "messages": [
      { "role": "user", "content": "Hello! How are you?" }
    ]
  }'
```

Interactive docs: http://localhost:8000/docs

Optional: Azure OpenAI agent
- Set environment variables: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and `AZURE_OPENAI_ENDPOINT` (or `AZURE_OPENAI_BASE_URL`).
- If present, the API will register an additional `azure` agent on startup.

## Example response (HTTP)

```json
{
  "messages": [
    { "role": "assistant", "content": "Hello! How can I help you today?", "message_id": "uuid-here" }
  ],
  "status": "completed",
  "conversation_id": "test-conversation"
}
```

## Alignment with the .NET implementation

| Area | .NET | Python POC |
| --- | --- | --- |
| Actor model | Channels + Tasks | asyncio.Queue + Tasks |
| State storage | CosmosDB + InMemory | InMemory (extensible via interface) |
| HTTP surface | ASP.NET Core | FastAPI |
| Streaming | IAsyncEnumerable | Handle-level updates (no HTTP streaming yet) |
| Telemetry | OpenTelemetry | Not implemented |

## Roadmap (architecture)

1) Streaming over HTTP (server-sent events or websockets) mapping to runtime progress updates.
2) Durable storage providers (e.g., Redis, Cosmos DB, PostgreSQL); thread serialization format.
3) Supervision: actor failure handling and restart policies.
4) Observability: structured logs + metrics + tracing (OpenTelemetry).
5) Multi-process/distributed actors (HTTP/gRPC between nodes).

---

Scope note: This is a proof-of-concept focused on the actor runtime shape and framework integration. It’s not production-ready; the emphasis is clarity of architecture and parity with the .NET concepts.