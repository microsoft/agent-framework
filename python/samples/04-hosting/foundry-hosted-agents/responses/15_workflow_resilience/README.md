# Durable workflow recovery

This sample shows a long-running background request continuing after its host
process is interrupted and replaced.

The request runs through a deterministic local pipeline:

```text
ingest -> transform -> validate -> finalize
```

No model deployment, external service, credentials, or environment variables
are required.

## Run the demo

From the repository's `python` directory:

```powershell
uv run python .\samples\04-hosting\foundry-hosted-agents\responses\15_workflow_resilience\demo.py
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
6. Verifies that completed stages were preserved and the final response output
   survived both interruptions.

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
uv run python .\samples\04-hosting\foundry-hosted-agents\responses\15_workflow_resilience\main.py
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
