# Multi-channel hosting samples

End-to-end samples for serving an `agent-framework` agent (or workflow)
through one or more **channels** with `agent-framework-hosting`.

The general hosting plumbing lives in
[`agent-framework-hosting`](../../../packages/hosting); each channel is
its own package. This first sample set includes
`agent-framework-hosting-responses`.

| Sample | What it shows | Packaging |
|---|---|---|
| [`local_responses/`](./local_responses) | The minimal shape: one agent + one `@tool` + native FastAPI route + Responses helper functions + `SessionStore`. | **Local only.** Start here to learn the helper seam. |
| [`local_responses_workflow/`](./local_responses_workflow) | A 4-step `Workflow` (typed `SloganBrief` intake → writer → legal → formatter) hosted behind the Responses channel via a `run_hook` that parses inbound text/JSON into the workflow's typed input. The host writes per-conversation checkpoints via `checkpoint_location=…`. Demonstrates workflow targets + structured input adaptation + resume-across-turns. Includes a `call_server.rest` file with REST examples. | **Local only.** |
| [`local_telegram/`](./local_telegram) | Telegram bot with `@tool`, `FileHistoryProvider`, `run_hook`, and slash commands (`/new`, `/whoami`, `/weather`). Pure Telegram — no HTTP endpoint. | **Local only.** Start here to learn the Telegram channel. |
| [`local_multi_channel/`](./local_multi_channel) | Same agent behind two channels at once: `ResponsesChannel` + `TelegramChannel`. Shared `FileHistoryProvider` enables cross-channel session resumption (resume a Telegram chat from the Responses endpoint by passing the Telegram isolation key as `previous_response_id`). | **Local only.** |

Each sample is fully self-contained — its own `pyproject.toml`, `uv.lock`,
server `app.py`, calling script(s), and `storage/` directory. Every
sample uses `[tool.uv.sources]` to wire its `agent-framework-hosting*`
dependencies to the
[`main`](https://github.com/microsoft/agent-framework/tree/main)
branch of the upstream repo via git refs, so they install cleanly outside
the monorepo while the hosting packages are still pre-PyPI. Once those
packages publish, drop the `[tool.uv.sources]` block and let the
declared deps resolve from PyPI.

## Relationship to `../foundry-hosted-agents/`

The sibling [`../foundry-hosted-agents/`](../foundry-hosted-agents) directory
contains samples for the **`agent-framework-hosted`** stack — agents
that run **inside** the Foundry Hosted Agents platform using its
built-in protocol surface (Responses, Invocations, conversation store,
isolation, identity), with **no `agent-framework-hosting` package
involved**.

| Aspect | `af-hosting/` (this directory) | `foundry-hosted-agents/` |
|---|---|---|
| Server stack | `agent-framework-hosting` + `agent-framework-hosting-responses` | `agent-framework-hosted` only — the Foundry Hosted Agents runtime owns the HTTP surface |
| Channels | Responses only in this initial sample set | The platform exposes Responses + Invocations |
| Run target | Local Hypercorn (`local_responses/`, `local_responses_workflow/`) | Hosted Agents *or* local container; targets the Hosted Agents platform contract |
| When to pick this | You want to learn the host/channel seams locally or need custom hosting middleware | You want zero hosting boilerplate, leveraging the Foundry-managed surface |

The table above summarizes the cross-sample story.
