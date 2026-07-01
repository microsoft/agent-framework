---
name: hosting-sample-runner
description: Decide how to validate a hosting sample (for example anything under 04-hosting that starts a server, function host, or deployed agent). Use when a sample hosts an agent or workflow and is run by starting a local server/host and calling it, or by deploying to a cloud provider.
license: MIT
compatibility: Works with any model that supports tool use.
metadata:
  author: agent-framework-samples
  version: "1.0"
---

## Usage

Hosting samples are different from ordinary scripts: instead of running to
completion, they typically start a server, function host, or hosted agent and
are exercised by a separate client call. Each hosting sample includes a
`README.md` that documents how to set up and run it.

When validating a hosting sample:

1. Read the sample's `README.md` (and any sibling READMEs in parent
   directories) to understand how the sample is meant to be run.
2. Decide whether the sample can be run **locally** — that is, fully exercised
   on this machine without deploying to a cloud provider (for example Azure
   Functions deployment, an Azure Container App, or a Foundry hosted-agent
   publish step). A sample is locally runnable when its README describes a
   local launch path, such as starting a local server (e.g. Hypercorn,
   `uv run python app.py`, the Functions Core Tools `func start`, or a durable
   task worker) and then calling it from a local client/HTTP request.

### If the sample can be run locally

Follow the README's local setup and run instructions:

1. Install any required dependencies it lists.
2. Start the host process in the background (it will not exit on its own).
3. Exercise it as the README describes — run the companion client script,
   send the documented HTTP request, or otherwise drive a single end-to-end
   interaction.
4. If the interaction succeeds, stop the host process and mark the sample as
   `success`.
5. If the host fails to start or the interaction errors, treat it as a
   `failure` and investigate the error.

### If the sample cannot be run locally

If the README only documents a cloud deployment path (for example deploying
to Azure Functions, publishing a Foundry hosted agent, or otherwise requiring
provisioned cloud infrastructure to exercise the sample), do not attempt to
deploy it. Mark the sample as `missing_setup` and note in the output that it
requires cloud deployment that cannot be performed locally.
