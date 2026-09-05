# Using-E2E-Resilience

This local E2E runs
[`Hosted-Workflow-Resilient-Long-Running`](../Hosted-Workflow-Resilient-Long-Running/)
through two recovery scenarios:

1. `Crash`, which terminates the hosted workflow process abruptly.
2. `Shutdown`, which follows the graceful shutdown path and defers the response for recovery.

> **Sample only.** The E2E, HTTP client, and SQLite service demonstrate resilience and idempotency.
> Do not use them as-is in production. The database insert is the simulated operation; no real email,
> payment, or other external action is performed.

## Three processes

The E2E uses three processes while each scenario is running:

| Process | Responsibility |
| --- | --- |
| `Using-E2E-Resilience` | Drives the scenario and consumes the recovered stream. |
| `Hosted-Workflow-Resilient-Long-Running` | Runs the resilient countdown workflow. |
| `Using-E2E-Resilience --idempotent-service` | Runs `IdempotentService` on Kestrel and stores operations in SQLite. |

The idempotent service is a class inside this sample, not a separate project or demo. The E2E
launches another instance of its own executable with `--idempotent-service`. That process runs only
the service, not the Crash and Shutdown scenarios, and remains running while the hosted workflow
process is replaced.

Both the hosted workflow and the E2E use `IdempotentServiceClient` from
`Hosted_Shared_Contributor_Setup`:

1. The hosted workflow posts operations to the idempotent service.
2. The idempotent service stores them in SQLite.
3. The E2E queries the same service for the completed operation count.

The workflow calls the service for every countdown value. The service stores each operation once
using `(scope, operation_id)` as the SQLite primary key. If recovery repeats a workflow step, the
service returns the existing result instead of creating another row.

## Current flow

`Program.cs` sets `interruptNumberMessage` to `"10"`. The hosted workflow adds ten to that numeric
input, so the countdown starts at 20 and the E2E interrupts it when it receives `10`.

1. Build the hosted server and start the idempotent service and hosted server on separate loopback ports.
2. Start a streaming background response. Read its first update and save the continuation token.
3. Dispose that initial stream enumerator. This closes the client stream, not the accepted background operation.
4. Open a second stream with the token and interrupt the hosted process at the selected count.
5. Start a replacement hosted process with the same workflow state, service endpoint, and operation scope.
6. Open a third stream using the original token, then query the service for the completed operation count.

The recovered stream is consumed independently of the second request. The client displays all text
updates and labels repeated text within that third request. It does not execute operations or
remove duplicates. With the current input, the expected database count is 20. The E2E prints the
returned count; it does not assert the count or the exact stream sequence.

## Why idempotency matters

An operation can finish at the service before the workflow's progress is durably confirmed. If the
hosted process stops during that interval, recovery may execute the step and call the service again.
The service's primary key makes the repeated call return the saved result without adding another row:

```text
Operation Crash/10 executed.
Duplicate operation Crash/10 ignored.
```

Those are service log messages. Repeated text in the client stream can come from replaying old events
or running an unconfirmed step again, so repeated text alone does not prove a second service effect.
The timing of interruption determines whether the step must run again.

**Workflow recovery, stream replay, and service idempotency have different jobs.** Checkpoints restore
workflow progress. Replay lets a client receive stored events again. Idempotency protects the
service's operation from being applied twice. Neither replay nor a checkpoint undoes an email or
payment already performed. Real downstream services must enforce that protection themselves.

## Internal service mode

The E2E starts service mode automatically with a random loopback address in `ASPNETCORE_URLS` and an
isolated SQLite file in `IDEMPOTENT_SERVICE_DATABASE_PATH`. Both are preserved while the hosted
workflow restarts. At the end, the E2E stops the service and removes temporary state on success.

Crash and Shutdown use separate temporary databases. Within each scenario, the service and its
database remain alive across both hosted process lifetimes. Failed scenarios retain their files and
print the paths for investigation; successful cleanup is best effort.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/readiness` | Reports that the service is ready. |
| `POST` | `/operations/{scope}/{operationId}` | Creates an operation or returns its stored result. |
| `GET` | `/operations/{scope}/count` | Returns the number of completed operations in the scope. |

## What normally triggers each path

Foundry sends `SIGTERM` when it intentionally stops a hosted agent container and can provide a
graceful shutdown window. This can happen during managed lifecycle operations such as session
compute deprovisioning, scale-in, or redeployment.

An abrupt crash provides no shutdown window. Typical examples include an application process crash,
a forced process termination, and an out-of-memory kill.

The local Shutdown scenario requests `StopAsync()` on the AgentServer task service, then stops the
web host. It exercises the shutdown signal without sending an OS signal on Windows. It does not
guarantee that a partially completed workflow step will never run again.

See [the hosted agent runtime contract](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-contract)
and [recovery guidance](https://learn.microsoft.com/azure/foundry/agents/how-to/recover-long-running-work).

## Run

No Azure project, model deployment, credentials, or second terminal is required. The E2E builds the
hosted workflow server and starts both server processes automatically.

From the repository root:

```powershell
dotnet run --project dotnet\samples\04-hosting\FoundryHostedAgents\responses\Using-E2E-Resilience
```

To change the demonstration, edit `interruptNumberMessage` in `Program.cs`. `--idempotent-service`
selects the internal service process instead of running the E2E scenarios.
