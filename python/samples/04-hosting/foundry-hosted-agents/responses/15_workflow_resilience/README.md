# Durable workflow recovery

This sample shows a long-running background request continuing after its host
process is interrupted and replaced.

The request runs through a deterministic local pipeline:

```text
ingest -> transform -> validate -> finalize
```

No model deployment, external service, credentials, or environment variables
are required.

## Private preview wheel setup

The private AgentServer preview wheels currently use the same package versions
as older public artifacts. Installing by package name or running the repository
workspace sync can therefore replace the preview build with the public build.

Create an isolated environment and install the local wheel files explicitly.
The Agent Framework wheel directory must contain
`agent_framework_core-*.whl` and
`agent_framework_foundry_hosting-*.whl`. The AgentServer wheel directory must
contain the `core`, `invocations`, and `responses` wheels.

PowerShell:

```powershell
$afWheels = "C:\path\to\agent-framework-wheels"
$agentServerWheels = "C:\path\to\agent-server-wheels"

uv venv .venv-preview
uv pip install --python .venv-preview\Scripts\python.exe `
    (Get-ChildItem "$afWheels\agent_framework_core-*.whl").FullName `
    (Get-ChildItem "$afWheels\agent_framework_foundry_hosting-*.whl").FullName `
    (Get-ChildItem "$agentServerWheels\azure_ai_agentserver_core-*.whl").FullName `
    (Get-ChildItem "$agentServerWheels\azure_ai_agentserver_invocations-*.whl").FullName `
    (Get-ChildItem "$agentServerWheels\azure_ai_agentserver_responses-*.whl").FullName `
    httpx
```

macOS/Linux:

```bash
export AF_WHEEL_DIR=/path/to/agent-framework-wheels
export AGENTSERVER_WHEEL_DIR=/path/to/agent-server-wheels

uv venv .venv-preview
uv pip install --python .venv-preview/bin/python \
    "$AF_WHEEL_DIR"/agent_framework_core-*.whl \
    "$AF_WHEEL_DIR"/agent_framework_foundry_hosting-*.whl \
    "$AGENTSERVER_WHEEL_DIR"/azure_ai_agentserver_core-*.whl \
    "$AGENTSERVER_WHEEL_DIR"/azure_ai_agentserver_invocations-*.whl \
    "$AGENTSERVER_WHEEL_DIR"/azure_ai_agentserver_responses-*.whl \
    httpx
```

Verify that the installed AgentServer build exposes the preview API:

```powershell
.venv-preview\Scripts\python.exe -c "from azure.ai.agentserver.responses import ResponsesServerOptions; assert ResponsesServerOptions(resilient_background=True).resilient_background"
```

```bash
.venv-preview/bin/python -c "from azure.ai.agentserver.responses import ResponsesServerOptions; assert ResponsesServerOptions(resilient_background=True).resilient_background"
```

Do not run `uv sync` in this environment. When using the repository workspace
environment instead, reinstall the three local AgentServer wheels after every
sync and run commands with `uv run --no-sync`.

## Run the demo

From the repository's `python` directory, using the isolated environment above:

```powershell
.venv-preview\Scripts\python.exe .\samples\04-hosting\foundry-hosted-agents\responses\15_workflow_resilience\demo.py
```

```bash
.venv-preview/bin/python ./samples/04-hosting/foundry-hosted-agents/responses/15_workflow_resilience/demo.py
```

Run `demo.py`, not `main.py`. `main.py` is the hosted agent server and waits for
API requests; `demo.py` starts that server and drives the complete scenario.

## What the demo proves

The demo:

1. Starts one background workflow request.
2. Stops the host while `transform` is running.
3. Starts a replacement host, which recovers the existing request.
4. Stops the replacement host while `finalize` is running.
5. Starts another replacement host and waits for the original request to
   complete.
6. Verifies that completed stages, intermediate progress output, and the final
   response output survived both interruptions.

The console shows only the customer-visible recovery story. Detailed server and
telemetry output is captured in an isolated diagnostic log and is printed only
if the demo fails.

Expected output:

```text
Durable workflow recovery demo
==============================
Pipeline: ingest -> transform -> validate -> finalize
The host will be interrupted twice while one request is running.

[START] Starting the first host instance...
[OK] Host is ready.

[REQUEST] Starting one background workflow request...
[OK] Request accepted: caresp_...
[OK] Initial status: in_progress

[WORKFLOW] Waiting for the first stage to complete...
[OK] 'ingest' completed and its progress was saved.
[INTERRUPT] Stopping the host while 'transform' is running...
[INTERRUPT] Host stopped unexpectedly.

[RECOVER] Starting a replacement host...
[OK] The existing request was recovered automatically.

[WORKFLOW] Waiting for two more stages to complete...
[OK] 'transform' and 'validate' completed; saved progress was preserved.
[INTERRUPT] Stopping the host while 'finalize' is running...
[INTERRUPT] Host stopped unexpectedly.

[RECOVER] Starting another replacement host...
[OK] The same request was recovered again.

[REQUEST] Waiting for the original request to finish...

Result
------
[OK] The original request completed after two host interruptions.
[OK] Progress output from every completed stage was preserved.
[OK] Final output: Pipeline complete for 'run the resilient pipeline'. Stages executed: ingest, transform, validate, finalize.
[OK] Every completed stage ran exactly once:
     ingest: 1
     transform: 1
     validate: 1
     finalize: 1

PASS: Durable progress and response output survived both interruptions.
```

## Application setup

The durability configuration in `main.py` is intentionally small:

```python
server = ResponsesHostServer(
    agent,
    options=ResponsesServerOptions(resilient_background=True),
)
```

The hosting layer manages durable workflow progress and recovers stored
background requests when a replacement host starts. The application does not
configure workflow checkpoint storage itself.

## Idempotency

An interrupted stage may restart from the beginning if its latest work had not
yet been saved. External side effects such as charging a payment, sending an
email, or writing to another system must use an idempotency key, upsert, or
equivalent duplicate-safe design.

The demo uses an append-only audit ledger to detect repeated completed work and
asserts that each completed stage appears exactly once.

## Manual server runs

To start only the hosted agent server:

```powershell
.venv-preview\Scripts\python.exe .\samples\04-hosting\foundry-hosted-agents\responses\15_workflow_resilience\main.py
```

```bash
.venv-preview/bin/python ./samples/04-hosting/foundry-hosted-agents/responses/15_workflow_resilience/main.py
```

The server then waits for Responses API requests on `http://localhost:8088`.
Use `Ctrl+C` to stop it.

`.env.example` documents optional settings for the workflow state directory,
stage delay, and local Azure Monitor Statsbeat behavior.

## Deploying to Foundry

Follow the parent sample's
[Foundry deployment instructions](../../README.md#deploying-the-agent-to-foundry).
In Foundry, host replacements exercise the same durable request recovery
behavior demonstrated locally.
