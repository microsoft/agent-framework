# local_a2a — WeatherAgent over A2A

This sample hosts a `WeatherAgent` using `AgentFrameworkHost` with `A2AChannel` and then
calls it from another process using `A2AAgent`.

## What this demonstrates

- Hosting an agent over the [A2A protocol](https://a2a-protocol.org/latest/) with
  `agent-framework-hosting-a2a`.
- A `run_hook` that strips caller-supplied generation options so the host
  controls model selection.
- `FileHistoryProvider` for cross-restart session continuity.
- Both non-streaming and streaming calls from a client using `A2AAgent`.

## Prerequisites

- Azure AI Foundry project endpoint and model name.
- `az login` (uses `DefaultAzureCredential`).

## Running

### 1. Start the server

```bash
uv sync
az login
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export FOUNDRY_MODEL=gpt-4o
uv run python app.py
```

The agent is now reachable at `http://localhost:8000/a2a`.

### 2. Run the client

In a second terminal:

```bash
uv run python call_client.py
```

The client resolves the hosted agent's A2A card, sends a weather question with
non-streaming, then sends another with streaming.

### Production-style multi-worker start

```bash
uv run hypercorn app:app --bind 0.0.0.0:8000
```
