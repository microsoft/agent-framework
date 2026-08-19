# Microsoft Agent Framework + OpenUI

This end-to-end sample connects [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) to
[OpenUI](https://github.com/thesysdev/openui) through Agent Framework's AG-UI endpoint. The result is a streaming
generative UI chat with charts, follow-up actions, validated forms, deterministic tools, and human approval.

## Responsibility Boundary

Both projects are required for the main flow:

```text
OpenUI AgentInterface
  -> latest user turn or approval resume
  -> Agent Framework AG-UI endpoint
  -> Agent Framework Agent, tools, model, and snapshot history
  -> streamed OpenUI Lang over AG-UI
  -> OpenUI parser, renderer, theme, forms, charts, and follow-up actions
```

- **Microsoft Agent Framework** owns model invocation, server-side conversation history, tools, approval pauses,
  and the AG-UI stream.
- **OpenUI** owns the chat shell, generated component prompt, OpenUI Lang parser and renderer, theme, charts,
  follow-up actions, and form state.
- `frontend/src/agent-framework.ts` is the small protocol seam. It sends only the newest turn because the
  `InMemoryAGUIThreadSnapshotStore` owns history. It also converts an approval action into AG-UI's canonical
  `availableInterrupts` and `resume` request.

The model's system prompt is generated from the same `openuiChatLibrary` object that `AgentInterface` renders.
The generated files are local build artifacts and are intentionally ignored by Git.

## Tested Versions

- `agent-framework-ag-ui` 1.1.0 from this repository checkout
- `agent-framework-openai` 1.13.0 from this repository checkout
- `@openuidev/react-ui` 0.13.6
- `@openuidev/react-lang` 0.2.11
- `@openuidev/cli` 0.2.8
- React 19.2.8 and Vite 8.0.16

The frontend lockfile is the source of truth for the JavaScript dependency graph.

## Folder Layout

- `backend/server.py`: Agent Framework agent, tools, approval policy, snapshot history, and FastAPI AG-UI endpoint
- `frontend/src/openui-library.ts`: committed OpenUI library and prompt options
- `frontend/src/agent-framework.ts`: AgentInterface transport, stream adapter, and approval resume mapping
- `frontend/src/App.tsx`: themed OpenUI `AgentInterface`
- `frontend/src/*.test.ts`: parser and action-transport contract tests
- `backend/generated/`: ignored OpenUI CLI output created by development and build commands

## Prerequisites

- Python 3.10+
- Node.js 20.19+ or 22.12+
- npm 9+
- An OpenAI API key available only to the backend process

Set these server-side environment variables in your shell:

- `OPENAI_API_KEY` (required)
- `OPENAI_MODEL` (optional, defaults to `gpt-5.4-nano`)

Never add a real key to the frontend or a tracked file.

## 1. Install Frontend Packages

From the repository root:

```bash
cd python/samples/05-end-to-end/openui_agent/frontend
npm install
```

## 2. Run the Backend

From the frontend directory after setting the environment variables:

```bash
npm run backend
```

This command regenerates `backend/generated/system-prompt.txt` and its library spec before it starts the backend.

- Health check: `http://127.0.0.1:8894/healthz`
- AG-UI endpoint: `POST http://127.0.0.1:8894/agent`

## 3. Run the Frontend

In a second terminal from the frontend directory:

```bash
npm run dev
```

Open `http://127.0.0.1:5173`. The development and production build commands regenerate the OpenUI prompt before
Vite starts or compiles.

To use a different backend URL:

```bash
VITE_BACKEND_URL=http://127.0.0.1:8894 npm run dev
```

## Acceptance Prompts

### Chart and follow-ups

```text
Show me our quarterly revenue.
```

Expected behavior: Agent Framework chooses the revenue tool. OpenUI renders its result as a visible chart and a
`FollowUpBlock`. Clicking a follow-up sends its text as one new user turn through the same Agent Framework thread.

### Validated form

```text
Create a project estimate form.
```

Use these non-secret values:

- Project name: `Aurora-731`
- Team size: `7`
- Notes: `Prioritize accessibility and charts`

Expected behavior: required-field validation blocks an incomplete submit. A valid submit sends the action context
and current form state through Agent Framework, and the next rendered response acknowledges the values.

### Agent Framework tool

```text
Show me our quarterly revenue.
```

Expected behavior: Agent Framework runs `get_quarterly_revenue`, streams its tool events, and the model turns the
result into rendered OpenUI.

### Human approval

```text
Publish the quarterly revenue report for executive leadership.
```

Expected behavior: The agent infers that it needs the revenue data, fetches it, proposes a report title and audience,
then pauses `publish_revenue_report` and emits a canonical interrupt. The adapter renders a visual OpenUI review
card from the proposed tool arguments. Approving sends one canonical AG-UI resume request and runs the synthetic
publishing tool. Rejecting sends `approved: false` and leaves that tool unexecuted.

## Validation Commands

From the frontend directory:

```bash
npm test
npm run build
```

From the repository's `python/` directory:

```bash
uv run poe syntax -S
uv run poe pyright -S
```

If `frontend/src/openui-library.ts` changes, regenerate the local prompt explicitly with:

```bash
npm run generate:openui
```

## Production Notes

This sample intentionally uses in-memory storage and maps every request to the single scope `"demo"`. AG-UI thread
IDs are not authorization boundaries. A production service must authenticate requests, map each user or tenant to
an isolated snapshot scope, use durable storage, and apply its own rate limits and CORS policy.

The approval tool has a synthetic result and does not publish to an external system.
