# Hosted-Workflow-Resilient-Long-Running

A deterministic countdown workflow that demonstrates resilient background execution. Each number is
one workflow output item. The workflow calls a separate idempotent HTTP service before emitting each
number. If the process stops, AgentServer supplies its saved response and MAF resumes the workflow
from the checkpoint referenced by that response.

> **Sample only.** This workflow, its HTTP client, and the backing service illustrate recovery and
> idempotency. Do not use them as-is in production. The service simulates an operation by inserting a
> SQLite record; it does not make arbitrary downstream actions transactional.

The input must be a single message containing integer text. The start executor adds ten so the E2E
has some progress to interrupt. With input `10`, a normal run emits:

```text
20
19
...
11
10
...
1
```

At zero, the workflow terminates without a visible completion message. A recovered stream can
include repeated text; this is separate from whether the service created duplicate operation records.

## Workflow

| Executor | Behavior |
| --- | --- |
| `start` | Parses the single text input as an integer, adds ten, and sends it to `countdown`. |
| `countdown` | Waits one second, calls the idempotent service, yields the returned number, and sends the decremented number to itself. |
| `complete` | Receives an empty string when the count reaches zero and ends the workflow. |

All executor IDs and the workflow agent ID are stable so a replacement process reconstructs the same
workflow topology.

## Idempotent operations

The countdown calls `IdempotentServiceClient` from `Hosted_Shared_Contributor_Setup`. The
[`Using-E2E-Resilience`](../Using-E2E-Resilience/) executable hosts the backing Kestrel service in a
separate process when started with `--idempotent-service`. Only that service accesses SQLite.

The service uses `(scope, operation_id)` as the primary key. The count is the operation ID. The first
call creates a row containing its result:

```text
Operation Crash/10 executed.
```

If recovery executes the same countdown step again, the insert leaves that row unchanged and the
service reads and returns its stored result:

```text
Duplicate operation Crash/10 ignored.
```

Configure the service with `IDEMPOTENT_SERVICE_ENDPOINT` and identify the logical operation group
with `IDEMPOTENT_OPERATION_SCOPE`. Keep the scope unchanged across recovery attempts. Use a different
scope for an unrelated run, otherwise the same counts intentionally reuse the previous results.

The service can complete an operation before the workflow's progress is confirmed. A crash or
shutdown during that interval can cause the step to be invoked again. The stable key protects the
database operation, not the execution of the workflow step or the text displayed by a client.
For a real email, payment, or API write, the downstream service must enforce equivalent idempotency.
Simply placing that external call beside a SQLite insert would not make the two actions atomic.

## Recovery boundary

After the workflow finishes a batch of work and creates its execution checkpoint, MAF Hosting:

1. Closes any remaining response output for that work.
2. Saves the matching AgentSession.
3. Writes the workflow checkpoint ID to AgentServer internal response metadata as
   `_last_checkpoint_id`.
4. Emits the updated `response.in_progress` state so AgentServer's authoritative response includes
   the internal metadata.
5. Yields `ResponseEventStream.Checkpoint()`.

On recovery, the handler reads `_last_checkpoint_id` from `PersistedResponse` and selects that exact
workflow checkpoint before execution continues. `PersistedResponse` is the saved response supplied
by AgentServer, not the client's accumulated text.

Workflow checkpoints, AgentSession storage, response storage, and the replay log are not one
transaction. Output can be published before its matching checkpoint is confirmed. Recovery can
therefore rerun unconfirmed work. A later `response.in_progress` event carries replacement response
state for clients that reconstruct the current result; it does not reverse an external service call.
See [streaming with reconnect](https://learn.microsoft.com/azure/foundry/agents/how-to/stream-with-reconnect).

## Local development

The easiest local demonstration is the automated E2E console:

```powershell
dotnet run --project dotnet\samples\04-hosting\FoundryHostedAgents\responses\Using-E2E-Resilience
```

It runs both an abrupt process crash and a host shutdown after a countdown operation, starts a
replacement process for each scenario, displays replayed output, and queries the idempotent service
for its completed operation count. The current input is `10`, so 20 stored operations are expected.
The E2E reports the count rather than asserting it. The shutdown path exercises `IsShutdownRequested`
and recovery deferral.

To run the components manually, start the service from the repository root in a separate terminal:

```powershell
$env:ASPNETCORE_URLS = "http://localhost:8089"
$env:IDEMPOTENT_SERVICE_DATABASE_PATH = Join-Path $env:TEMP "countdown-idempotency.db"
dotnet run --project dotnet\samples\04-hosting\FoundryHostedAgents\responses\Using-E2E-Resilience -- --idempotent-service
```

In this hosted sample's directory, copy `.env.example` to `.env`, configure the service endpoint and
scope, and run `dotnet run`. Send integer text such as `"10"` to the Responses endpoint. Closing the
HTTP stream of an accepted background response does not cancel its server-side execution.

## Deploy from source

Before deployment, provide an appropriately secured idempotent service reachable from the Foundry
container. Set `IDEMPOTENT_SERVICE_ENDPOINT` and `IDEMPOTENT_OPERATION_SCOPE` in the azd environment.
A local `localhost:8089` service is not reachable from a deployed container.

Create an empty working directory outside the repository:

```powershell
$work = Join-Path $env:TEMP "hosted-workflow-resilient-long-running-work"
New-Item -ItemType Directory -Path $work -Force | Out-Null
Set-Location $work

$sample = "<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Workflow-Resilient-Long-Running/azure.yaml"
azd auth login
azd ai agent init -m $sample
```

### Contributors testing framework changes

Skip this section unless the current framework changes have not been released. Pack the repository
source into the scaffolded upload before provisioning:

```powershell
<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/scripts/Add-LocalFrameworkFeed.ps1 `
    -Path ./hosted-workflow-resilient-long-running
```

Then deploy:

```powershell
Set-Location hosted-workflow-resilient-long-running
azd provision
azd deploy
```

Grant the hosted agent identity `Foundry User` on the Foundry project so it can write workflow
checkpoints and AgentSession state.

## Automated coverage

`ResilientTwoLifetimeIntegrationTests.StoppedHost_RecoversWorkflowWithCompleteOrderedOutputAsync`
uses its own test workflow, not these sample executors. It starts the Responses host twice over
shared durable state, interrupts the first host while its counter is processing `3`, and verifies:

```text
6, 5, 4, 3, 2, 1, Countdown complete.
```

## Related samples

- [Using-E2E-Resilience](../Using-E2E-Resilience/README.md): automated crash and shutdown recovery console.
- [Hosted-Workflow-Resilient](../Hosted-Workflow-Resilient/README.md): resilient model-backed translation workflow.
- [Hosted-Workflow-Simple](../Hosted-Workflow-Simple/README.md): workflow hosting without resilient background execution.
- [Hosted-Steering](../Hosted-Steering/README.md): mid-turn steering.
