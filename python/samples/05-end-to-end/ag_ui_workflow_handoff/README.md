# AG-UI Handoff Workflow Demo

This demo is a full custom AG-UI application built on top of the new workflow abstractions in `agent_framework_ag_ui`.

It includes:

- A **backend** FastAPI AG-UI endpoint serving a **HandoffBuilder workflow** with:
  - `triage_agent`
  - `refund_agent`
  - `order_agent`
- Required **tool approval checkpoints**:
  - `submit_refund` (`approval_mode="always_require"`)
  - `submit_replacement` (`approval_mode="always_require"`)
- A second **request-info resume** step (order agent asks for shipping preference)
- A **frontend** React app that consumes AG-UI SSE events, renders workflow cards, and sends `resume.interrupts` payloads.

The backend uses Azure OpenAI responses and supports intent-driven, non-linear handoff routing.

This demo keeps workflow state per `thread_id`. When the assistant ends a case with `Case complete.`, the UI blocks
later top-level input on that same thread and asks the user to start a new case explicitly instead of resuming a
terminated workflow.

## Folder Layout

- `backend/server.py` - FastAPI + AG-UI endpoint + Handoff workflow
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
uv run python samples/05-end-to-end/ag_ui_workflow_handoff/backend/server.py
```

Backend default URL:

- `http://127.0.0.1:8891`
- AG-UI endpoint: `POST http://127.0.0.1:8891/handoff_demo`

## 2) Install Frontend Packages (npm)

From the `python/` directory (where Step 1 left you):

```bash
cd samples/05-end-to-end/ag_ui_workflow_handoff/frontend
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
VITE_BACKEND_URL=http://127.0.0.1:8891 npm run dev
```

## 4) Demo Flow to Verify

1. Click one of the starter prompts (or type a refund request).
2. Refund Agent asks for an order number; reply with a numeric ID (for example: `987654`).
3. If your initial request did not explicitly choose refund vs replacement, the agent asks a clarifying choice question.
4. Wait for the `submit_refund` reviewer interrupt (built from your provided order ID).
5. In the **HITL Reviewer Console** modal, click **Approve Tool Call**.
6. If you asked for replacement, the Order agent asks for shipping preference; reply in the chat input (for example: `expedited`).
7. When replacement is requested, wait for the `submit_replacement` reviewer interrupt and approve/reject it.
8. If you asked for refund-only, the flow should close without replacement/shipping prompts.
9. Confirm the case snapshot updates and workflow completion.
10. After the case closes, another top-level message on the same thread is rejected with a notice.
11. Click **Start New Case** to begin a fresh thread.

## Important: `require_per_service_call_history_persistence`

All agents participating in a handoff workflow **must** be constructed with
`require_per_service_call_history_persistence=True`. The `HandoffBuilder` will
raise a `ValueError` at build time if any participant is missing this flag.

**Why this is required:** Handoff workflows use middleware that short-circuits
tool calls via `MiddlewareTermination` when a handoff tool is invoked. Without
per-service-call history persistence, local history providers would persist tool
results that the service never received, causing call/result mismatches on
subsequent turns.

```python
agent = Agent(
    client=client,
    name="my_agent",
    require_per_service_call_history_persistence=True,  # Required for handoff
)
```

## What This Validates

- `add_agent_framework_fastapi_endpoint(...)` with `AgentFrameworkWorkflow(workflow_factory=...)`
- Thread-scoped workflow state across turns
- `RUN_FINISHED.interrupt` pause behavior
- `resume.interrupts` continuation behavior
- JSON resume payload coercion for `Content` and `list[Message]` workflow response types
- Intent-driven routing between triage, refund, and order specialists (no forced linear path)
- Multiple HITL approvals in one case (`submit_refund` + `submit_replacement`)
