# Hosted-Workflow-Resilient-Long-Running

A deterministic countdown workflow that demonstrates resilient background execution. Each number is
one workflow output item. If the process stops, AgentServer restores the last response snapshot and
the workflow resumes from the exact workflow checkpoint ID recorded in that snapshot.

For an input such as `Count down from 6`, the final message outputs are:

```text
6
5
4
3
2
1
Countdown complete.
```

The exact list makes recovery errors visible. A missing item means response state advanced beyond
workflow state. A repeated item means the workflow resumed before the response snapshot boundary.

## Workflow

| Executor | Behavior |
| --- | --- |
| `start` | Reads the first positive integer from the request. |
| `countdown` | Waits, yields the current number, decrements it, and sends it back to itself. |
| `complete` | Yields `Countdown complete.` after the counter reaches zero. |

All executor IDs and the workflow agent ID are stable so a replacement process reconstructs the same
workflow topology.

## Recovery boundary

At every completed workflow superstep, Foundry Hosting:

1. Closes the response output item produced by that superstep.
2. Saves the matching AgentSession.
3. Writes the workflow checkpoint ID to AgentServer internal response metadata as
   `_last_checkpoint_id`.
4. Emits the updated `response.in_progress` state so AgentServer's authoritative response includes
   the internal metadata.
5. Yields `ResponseEventStream.Checkpoint()`.

On recovery, the handler reads `_last_checkpoint_id` from `PersistedResponse` and selects that exact
workflow checkpoint before execution continues.

## Local development

The easiest local demonstration is the automated E2E console:

```powershell
dotnet run --project dotnet\samples\04-hosting\FoundryHostedAgents\responses\Using-E2E-Resilience
```

It starts this server, prints countdown outputs, force-kills the process, restarts it, prints replay
and recovery outputs, and validates the final sequence.

To run only the server, copy `.env.example` to `.env`, then run:

```powershell
dotnet run --tl:off
```

Set `COUNTDOWN_DELAY_SECONDS=0` to make a normal run complete immediately.

## Deploy from source

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
starts the Responses host twice over shared durable state. It interrupts the first host while the
counter is processing `3`, then verifies that the recovered response contains exactly:

```text
6, 5, 4, 3, 2, 1, Countdown complete.
```

## Related samples

- [Using-E2E-Resilience](../Using-E2E-Resilience/README.md): automated local crash-recovery console.
- [Hosted-Workflow-Resilient](../Hosted-Workflow-Resilient/README.md): resilient model-backed translation workflow.
- [Hosted-Workflow-Simple](../Hosted-Workflow-Simple/README.md): workflow hosting without resilient background execution.
- [Hosted-Steering](../Hosted-Steering/README.md): mid-turn steering.
