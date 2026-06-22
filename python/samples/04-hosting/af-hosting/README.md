# Multi-channel hosting samples

End-to-end samples for serving an `agent-framework` agent (or workflow)
through one or more **channels** with `agent-framework-hosting`.

The general hosting plumbing lives in
[`agent-framework-hosting`](../../../packages/hosting); each channel is
its own package. This first sample set includes
`agent-framework-hosting-responses`.

| Sample | What it shows | Packaging |
|---|---|---|
| [`local_responses/`](./local_responses) | The minimal shape: one agent + one `@tool` + `ResponsesChannel` + a single `run_hook` that strips caller-supplied options and forces a `reasoning` preset. | **Local only.** Start here to learn the run-hook seam. |
| [`local_responses_workflow/`](./local_responses_workflow) | A 3-step `Workflow` (writer → legal → formatter) hosted behind the Responses channel via a `run_hook` that parses inbound text/JSON into the writer prompt. The host writes per-conversation checkpoints via `checkpoint_location=…`. Demonstrates workflow targets + input preparation + resume-across-turns. Includes a `call_server.rest` file with REST examples. | **Local only.** |

Each sample is fully self-contained — its own `pyproject.toml`, `uv.lock`,
server `app.py`, calling script(s), and `storage/` directory. Every
sample uses `[tool.uv.sources]` to wire its `agent-framework-hosting*`
dependencies to the
[`main`](https://github.com/microsoft/agent-framework/tree/main)
branch of the upstream repo via git refs, so they install cleanly outside
the monorepo while the hosting packages are still pre-PyPI. Once those
packages publish, drop the `[tool.uv.sources]` block and let the
declared deps resolve from PyPI.

## Relationship to Foundry Hosted Agents

These samples are **not** the recommended hosting path for Foundry Hosted
Agents. They are local/custom-ASGI samples for learning the generic
`agent-framework-hosting` host/channel seams.

For Foundry Hosted Agents, use the `agent-framework-foundry-hosting`
package and the Foundry hosting samples. That stack targets the Foundry
Hosted Agents platform contract and owns the platform-specific HTTP
surface, conversation store, isolation, and identity behavior.

| Aspect | `af-hosting/` (this directory) | Foundry Hosted Agents |
|---|---|---|
| Server stack | `agent-framework-hosting` + channel packages | `agent-framework-foundry-hosting` |
| Channels | Self-managed channel packages such as Responses | Foundry-managed protocol surface |
| Run target | Local Hypercorn or your own ASGI host | Foundry Hosted Agents platform |
| When to pick this | You want to learn host/channel seams locally or need custom ASGI hosting | You are deploying to Foundry Hosted Agents |

The table above summarizes the cross-sample story.
