# AG-UI Single Agent Demo

The simplest possible AG-UI integration: a **single chat agent** with **no tools** and **no context providers**,
served over the AG-UI protocol and consumed by a small React client.

Use this sample as the starting point for AG-UI. For a richer, multi-agent example with tool-approval checkpoints
and human-in-the-loop resumes, see [`../ag_ui_workflow_handoff`](../ag_ui_workflow_handoff/README.md).

## Folder Layout

- `backend/server.py` - FastAPI + AG-UI endpoint wrapping a single `Agent`
- `frontend/` - Vite + React AG-UI client UI

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm 9+
- Azure AI project + model deployment configured in environment variables:
  - `FOUNDRY_PROJECT_ENDPOINT`
  - `FOUNDRY_MODEL`

## 1) Run Backend

From the Python repo root:

```bash
cd python
uv sync
uv run python samples/05-end-to-end/ag_ui_single_agent/backend/server.py
```

Backend default URL:

- `http://127.0.0.1:8892`
- AG-UI endpoint: `POST http://127.0.0.1:8892/agent`

## 2) Install Frontend Packages (npm)

From the `python/` directory (where Step 1 left you):

```bash
cd samples/05-end-to-end/ag_ui_single_agent/frontend
npm install
```

## 3) Run Frontend Locally

```bash
npm run dev
```

Frontend default URL:

- `http://127.0.0.1:5173`

If you changed backend host/port, run with:

```bash
VITE_BACKEND_URL=http://127.0.0.1:8892 npm run dev
```

## 4) Demo Flow to Verify

1. Click one of the starter prompts (or type your own message).
2. Watch the assistant response stream in token by token.
3. Send a follow-up that depends on the previous turn (for example: "summarize what you just told me").
   The client only sends the newest message plus the `thread_id`; the server replays the stored history.
4. Click **New Thread** to start a fresh conversation (a new `thread_id`).

## Conversation History

The client only ever sends the **newest message** plus a `thread_id`. The backend retains history **server-side**,
keyed by that `thread_id`, using an `InMemoryAGUIThreadSnapshotStore`. Because an AG-UI thread id is not an
authorization boundary, a `snapshot_scope_resolver` is required whenever a snapshot store is configured; this
single-tenant demo maps every request to one shared `"demo"` scope.

The in-memory store is process-local and not durable. Swap in your own `AGUIThreadSnapshotStore` implementation
(and a real scope resolver) for production.

## What This Validates

- `add_agent_framework_fastapi_endpoint(...)` with a plain `Agent` (no `AgentFrameworkWorkflow` wrapper)
- Streaming assistant text via `TEXT_MESSAGE_START` / `TEXT_MESSAGE_CONTENT` / `TEXT_MESSAGE_END` AG-UI events
- Server-side conversation history keyed by `thread_id` via a snapshot store
