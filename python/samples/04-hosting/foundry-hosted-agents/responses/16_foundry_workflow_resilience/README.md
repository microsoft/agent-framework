# Resilient translation workflow

This sample adapts the Foundry three-agent translation workflow into a durable
background request:

```text
English -> French -> Spanish -> English
```

Each stage intentionally terminates its host once, then calls a real model
through `FoundryChatClient` after recovery. Before exiting, the stage atomically
writes and flushes a marker in the session's persistent home directory. The
replacement host sees that marker and continues instead of crashing again.
After the recovered stage completes, it removes its marker so a later workflow
request demonstrates the same three crashes again.
`ResponsesServerOptions(resilient_background=True)` keeps the original
background response and workflow checkpoints alive across all three restarts.

`azure.yaml` defines the `azd` project and provisioned services. The source
directory's `agent.yaml` is an Agent Manifest with the required `template`
field. It is intentionally not a ContainerAgent-schema document; current `azd`
validates `agent.yaml` against the Agent Manifest schema.

## Prerequisites

1. Install `azd` and the Foundry agents extension declared by `azure.yaml`:

   ```powershell
   azd extension install azure.ai.agents
   azd extension upgrade azure.ai.agents
   azd auth login
   az login
   ```

2. Obtain these private preview wheels:

   - `agent_framework_foundry_hosting-*.whl`
   - `azure_ai_agentserver_core-*.whl`
   - `azure_ai_agentserver_invocations-*.whl`
   - `azure_ai_agentserver_responses-*.whl`

The AgentServer preview uses the same package versions as public artifacts.
The wheels must therefore be installed by file, not resolved by package name.

## Prepare the deployment

From this directory:

```powershell
python .\prepare_wheels.py `
  --agent-framework-wheels C:\path\to\agent-framework-wheels `
  --agent-server-wheels C:\path\to\agent-server-wheels
```

The script requires exactly one matching wheel for each package, verifies that
the Responses wheel contains the private durability API, copies the four files
into the container build context, and generates `wheelhouse/private-wheels.txt`
with their actual filenames. This rejects the same-version public Responses
wheel before deployment. The generated files are intentionally gitignored, but
`.agentignore` explicitly includes them in the Foundry code deployment ZIP.
`requirements.txt` includes the generated requirements fragment, so code
deployment does not fall back to public packages or depend on one build's wheel
filenames.

Initialize or select an `azd` environment, then provision:

```powershell
azd env new
azd provision
```

If you already have a Foundry project and model deployment, use the normal
`azd ai agent init` or environment configuration flow to target them.

## Run locally

```powershell
azd ai agent run
```

In another terminal:

```powershell
uv run .\durability_client.py --endpoint http://localhost:8088/responses
```

With `WORKFLOW_CRASH_ONCE_PER_STAGE=true`, the local host exits at the start of
each stage. Restart `azd ai agent run` after each exit while the client keeps
polling. Set the variable to `false` to run without injected crashes.

## Deploy and prove recovery

Deploy the container:

```powershell
azd deploy
azd ai agent show --output json
```

Create a hosted session with persistent filesystem state:

```powershell
azd ai agent sessions create --output json
```

Copy `agent_session_id` from the result and the Responses endpoint from
`azd ai agent show`, then start one stored background response bound to that
session:

```powershell
uv run .\durability_client.py `
  --endpoint "https://<account>.services.ai.azure.com/api/projects/<project>/agents/resilient-translation-workflow/endpoint/protocols/openai/responses?api-version=v1" `
  --session-id "<agent-session-id>"
```

The first attempt at each translation stage persists a marker and exits with
code 70. Foundry automatically starts a replacement container with the same
session ID and persistent home directory. The client continues polling the
original response through all three replacements. The container logs show one
intentional termination and one recovered continuation for each stage. Each
marker is removed after its recovered stage succeeds, so another request in the
same session repeats the demonstration.

A successful run ends with the persisted French, Spanish, and round-trip
English output followed by:

```text
PASS: The original response completed.
```

The response ID and endpoint are also saved in `.durability-response.json`. If
the client itself is interrupted, resume polling with:

```powershell
uv run .\durability_client.py `
  --endpoint "<endpoint>" `
  --session-id "<agent-session-id>" `
  --response-id "<response-id>"
```

## Durability boundary

Workflow progress is saved between executor supersteps. If a host stops during
a model call, that current stage may run again; completed prior stages are
restored. Model translation is side-effect free. Production executors that
write to external systems must use idempotency keys, upserts, or an equivalent
duplicate-safe design.
