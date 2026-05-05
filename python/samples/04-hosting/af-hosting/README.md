# Multi-channel hosting samples

End-to-end samples for serving an `agent-framework` agent (or workflow)
through one or more **channels** with `agent-framework-hosting`.

The general hosting plumbing lives in
[`agent-framework-hosting`](../../../packages/hosting); each channel is
its own package (`agent-framework-hosting-responses`,
`agent-framework-hosting-invocations`,
`agent-framework-hosting-telegram`, `agent-framework-hosting-activity-protocol`,
`agent-framework-hosting-entra`).

| Sample | What it shows | Packaging |
|---|---|---|
| [`local_responses/`](./local_responses) | The minimal shape: one agent + one `@tool` + `ResponsesChannel` + a single `run_hook` that strips caller-supplied options and forces a `reasoning` preset. | **Local only.** Start here to learn the run-hook seam. |
| [`local_responses_workflow/`](./local_responses_workflow) | A 4-step `Workflow` (typed `SloganBrief` intake → writer → legal → formatter) hosted behind **both** the Responses and Invocations channels via a shared `run_hook` that parses inbound text/JSON into the workflow's typed input. The host writes per-conversation checkpoints via `checkpoint_location=…`. Demonstrates workflow targets + structured input adaptation + multi-channel + resume-across-turns. Includes a `call_server.rest` file with REST examples for both endpoints. | **Local only.** |
| [`foundry_hosted_agent/`](./foundry_hosted_agent) | One Foundry agent, **Responses + Invocations only** — the minimal shape that is **runtime-compatible with the Foundry Hosted Agents platform**. | Ships with `Dockerfile` + `agent.yaml` + `agent.manifest.yaml` + `azure.yaml` so the same image runs locally **or** as a Foundry Hosted Agent (`azd up`). |
| [`local_telegram/`](./local_telegram) | Adds Telegram, a `@tool`, `FileHistoryProvider`, run hooks (per-user / per-chat session keying), extra Telegram commands, and `ResponseTarget` multicast. Runs under Hypercorn with multiple workers. | **Local only.** No Dockerfile / Foundry packaging. |
| [`local_identity_link/`](./local_identity_link) | Everything in `local_telegram/` plus Teams and the Entra identity-link sidecar (`/auth/start` + `/auth/callback`). Demonstrates linking a Telegram chat to an Entra user so multiple non-Entra channels can share one isolation key. | **Local only.** No Dockerfile / Foundry packaging. |

Each sample is fully self-contained — its own `pyproject.toml`, `uv.lock`,
server `app.py`, calling script(s), and `storage/` directory. Every
sample uses `[tool.uv.sources]` to wire its `agent-framework-hosting*`
dependencies to the
[`feature/python-hosting`](https://github.com/microsoft/agent-framework/tree/feature/python-hosting)
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
| Server stack | `agent-framework-hosting` + per-channel packages (`-responses`, `-invocations`, `-telegram`, `-activity-protocol`, `-entra`) | `agent-framework-hosted` only — the Foundry Hosted Agents runtime owns the HTTP surface |
| Channels other than Responses / Invocations | Yes — Telegram, Activity Protocol (Teams), Entra identity-linking | No — the platform exposes Responses + Invocations only |
| Run target | Local Hypercorn (`local_responses/`, `local_telegram/`, `local_identity_link/`); Hosted Agents *or* local (`foundry_hosted_agent/`) | Hosted Agents *or* local container; targets the Hosted Agents platform contract |
| When to pick this | You need extra channels (Telegram/Teams via Activity Protocol/…), custom hosting middleware, or want to run outside the Foundry runtime | You only need Responses/Invocations and want zero hosting boilerplate, leveraging the Foundry-managed surface |

`foundry_hosted_agent/` is the bridge sample: it uses the
`agent-framework-hosting` stack but is packaged so the Foundry Hosted
Agents platform can run it as one of its own.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the cross-sample story.
