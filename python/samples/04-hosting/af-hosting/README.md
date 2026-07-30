# Agent Framework hosting helper samples

End-to-end samples for exposing Agent Framework targets through app-owned
hosting routes.

The helper-first hosting packages provide protocol conversion and optional
execution state. The application still owns the web framework, native SDK
clients, authentication, response construction, and deployment shape.

| Sample | What it shows | Packaging |
|---|---|---|
| [`local_responses/`](./local_responses) | One agent + one `@tool` + native FastAPI route + Responses helper functions + hosting `AgentState` + core `SessionStore`. | **Local only.** Start here to learn the helper seam. |
| [`local_responses_workflow/`](./local_responses_workflow) | A workflow target behind a native FastAPI route using Responses helper functions, `WorkflowState`, explicit `CheckpointStorage`, and an app-owned checkpoint cursor. | **Local only.** |
| [`local_telegram/`](./local_telegram) | One agent + `aiogram` polling + Telegram conversion helpers + app-owned commands, media policy, and streaming edits. | **Local only.** Requires a Telegram bot token. |

Each sample is self-contained with its own `pyproject.toml`, executable
application code, and `storage/` directory. HTTP samples also include calling
scripts. Samples use `[tool.uv.sources]`
to wire unreleased hosting packages to the upstream repo while those packages
are still pre-PyPI. Once those packages publish, drop the `[tool.uv.sources]`
block and let the declared dependencies resolve from PyPI.

## Relationship to `../foundry-hosted-agents/`

The sibling [`../foundry-hosted-agents/`](../foundry-hosted-agents) directory
contains samples for agents that run inside the Foundry Hosted Agents platform.
Those samples use the Foundry-managed protocol surface with no
`agent-framework-hosting` package involved.

| Aspect | `af-hosting/` (this directory) | `foundry-hosted-agents/` |
|---|---|---|
| Server stack | App-owned framework/native client + hosting protocol helpers | Foundry Hosted Agents runtime |
| Protocol surface | The app exposes the route and calls helpers | The platform exposes Responses + Invocations |
| Run target | Local Hypercorn (`local_responses/`, `local_responses_workflow/`) or native polling (`local_telegram/`) | Hosted Agents or local container targeting the Hosted Agents contract |
| When to pick this | You need custom hosting code or want to learn the helper seam | You want the Foundry-managed hosting surface |
