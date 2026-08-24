---
status: proposed
contact: rogerbarreto
date: 2026-08-21
deciders: rogerbarreto
consulted: Tao Chen, Sergey M., Ben Thomas, Shanmukha
informed: Agent Framework .NET team
---

# Resilient long-running agents in Microsoft.Agents.AI.Foundry.Hosting

## Context and Problem Statement

The Foundry Hosted Agents platform can run a hosted agent as a long job that continues when no
client is connected, and that the platform restarts after the container crashes or is recycled.
On restart the platform re-invokes the handler with the same input, sets `ResponseContext.IsRecovery`
to true, and supplies the last durable `ResponseObject` snapshot as `PersistedResponse`. The
snapshot is not itself a workflow checkpoint. For workflow agents, hosting records the ID of the
matching workflow checkpoint inside AgentServer internal response metadata before it persists the
response snapshot.

This applies only to **background** requests (`background=true`) whose `store` value is omitted or
true. Omitted `store` uses the Responses API default of true. Foreground requests and explicit
`store=false` requests have no crash-recovery contract.

Python currently supports resilient background execution for workflow agents and steering for
single agents. .NET hosting must offer the same opt-in capabilities on top of the durable session
and checkpoint storage introduced for Foundry state stores (PR #7649).

## Decision Drivers

- Match the Python recovery contract.
- Pair each persisted workflow response snapshot with the exact workflow checkpoint it represents.
- Opt-in and off by default; non-resilient hosts pay nothing.
- Prefer workflows: they already checkpoint between supersteps.
- Keep a lean API on `FoundryResponsesOptions`, forwarded to `ResponsesServerOptions`.
- Persist agent sessions through the Foundry state store (or its local fallback), not a second disk layout.

## Decision Outcome

Chosen option: **turn resilience on through the existing handler and registration path**.

### Public surface

`FoundryResponsesOptions.ResilientBackground` and `FoundryResponsesOptions.SteerableConversations`
are forwarded to `ResponsesServerOptions` so the AgentServer SDK enables recovery and steering.
This forwarding must happen in the callback passed directly to `AddResponsesServer`. The SDK makes
two process-level choices during that registration call: whether local SSE replay uses durable
storage and whether the conversation task accepts steering. Configuring the options only through
the later `IOptions` pipeline is too late for those choices.

The first `AddFoundryResponses` call owns this host-level configuration. Repeated calls do not
register another Responses server or redefine its resilience mode. Later calls can still configure
MAF-only options such as `AllowStoredOutputEnabled`; attempting to enable an AgentServer task
feature after the first call fails immediately instead of leaving AgentServer and MAF with
different settings.

```csharp
builder.Services.AddFoundryResponses(agent, configure: o => o.ResilientBackground = true);
```

### Handler contract on recovery

When `IsRecovery` is true:

1. Seed `ResponseEventStream` from the `PersistedResponse` that AgentServer provides. This preserves
   its response fields, completed output items, and internal metadata.
2. When the snapshot contains `_last_checkpoint_id` and a persisted workflow `AgentSession` was
   restored, select that exact checkpoint as the workflow resume point. This prevents a newer
   checkpoint already present in workflow storage from being combined with an older response
   snapshot. Foundry Hosting obtains the experimental `WorkflowSessionCheckpointRecovery` service
   from the restored `AgentSession`; the internal `WorkflowSession` remains hidden. The resumed run
   continues the work already queued in that checkpoint without sending a new `TurnToken` to the
   start executor.
3. When `_last_checkpoint_id` is absent, retain the checkpoint already referenced by the restored
   session. This covers a crash after the workflow wrote its first checkpoint but before AgentServer
   persisted the first paired response snapshot. If the process stopped before the first session
   save, no resumable MAF state exists, so the handler re-injects the original input instead of
   invoking a fresh session with no messages. A regular agent has no equivalent within-turn workflow
   checkpoint, so recovery remains best-effort and depends on its serialized session state.
4. On graceful shutdown of a resilient turn, call `ExitForRecoveryAsync` instead of emitting
   incomplete. The AgentServer shutdown token is linked to the token passed into the MAF agent so
   long-running model, tool, and workflow operations stop promptly. The handler also checks
   `IsShutdownRequested` after each agent update, because an agent may consume cancellation and
   return normally instead of throwing. If shutdown becomes visible after the agent advanced but
   before the corresponding event was emitted, the final session save is skipped. Recovery uses
   the last session snapshot that corresponds to output already handed to AgentServer.
5. For non-workflow agents, best-effort save the agent session after each
   `ResponseOutputItemDoneEvent`, with an authoritative end-of-turn save in `finally` (skipped when
   the turn failed). Workflow agents use only the paired superstep path below for incremental saves,
   so their persisted session cannot advance independently through ordinary output-item saves.

### Workflow response checkpoint alignment

When `OutputConverter` receives a `SuperStepCompletedEvent` with a new workflow checkpoint ID:

1. Close any response output item still open for that superstep.
2. Compare the new ID with `_last_checkpoint_id` in `ResponseEventStream.InternalMetadata`. If they
   match, do nothing.
3. Save the `AgentSession` that references the new workflow checkpoint. If this save fails, keep the
   prior response snapshot and metadata. The turn continues, and a later workflow checkpoint or the
   final save can try again.
4. Write the new ID to `_last_checkpoint_id`.
5. Emit `response.in_progress` with the updated response state. AgentServer beta.8 tracks a
   separate authoritative response object, so this event copies the internal metadata into the
   snapshot that its checkpoint operation persists. The reserved metadata remains stripped from
   client payloads.
6. Yield `ResponseEventStream.Checkpoint()`. AgentServer persists the response snapshot before it
   resumes the handler.

The workflow checkpoint itself is already durable before `SuperStepCompletedEvent` is emitted. The
session save and response checkpoint therefore establish a recoverable boundary with three matching
parts: completed response output, serialized session state, and workflow checkpoint ID.

If a crash occurs after the workflow creates a newer checkpoint but before the next response
checkpoint, recovery deliberately uses the older ID from `PersistedResponse`. The workflow may
repeat work after that older boundary, but it does not duplicate output already present in the
response snapshot or lose output by resuming ahead of it.

### Handler contract on steering

When a second input arrives for an active steerable conversation:

1. AgentServer returns a response with `status=queued`, records the input, increments
   `PendingInputCount` on the active handler context, and signals that handler's cancellation token.
2. The superseded handler invocation has `IsSteeredTurn=false`. If a cancellation-aware MAF
   operation throws `OperationCanceledException`, Foundry Hosting uses `PendingInputCount > 0` to
   distinguish steering from shutdown and client cancellation.
3. Foundry Hosting completes the superseded response cleanly and saves its `AgentSession` with a
   non-cancelled save token. This gives the queued turn the latest committed MAF state.
4. AgentServer invokes the handler again with `IsSteeredTurn=true`. This is not crash recovery:
   `IsRecovery=false`, so the new input is converted to MAF messages normally. The same
   `conversation_id` resolves the same persisted `AgentSession`.

No special MAF branch is required merely because `IsSteeredTurn=true`. The classification is
available for handlers that need different application behavior; the generic adapter treats the
drained input as the next normal turn on the same session.

Steering does not create a response checkpoint merely because another input was queued. Completed
workflow supersteps have already been paired with response checkpoints. An interrupted superstep
has no new `SuperStepCompletedEvent`, so its partial output and session state do not advance the
paired recovery boundary. The superseded response still reaches a terminal `completed` event.

### State ownership

| State | Owner | Recovery purpose |
|---|---|---|
| Resilient task, SSE events, `ResponseObject` snapshots, `_last_checkpoint_id` | AgentServer | Re-invoke the handler and identify the workflow checkpoint represented by each response snapshot |
| Serialized `AgentSession` | Foundry Hosting | Restore agent-owned state and the workflow checkpoint reference |
| Workflow execution checkpoints | Workflow runtime through `FoundryJsonCheckpointStore` | Restore executors, queued messages, pending requests, and workflow state |

The handler calls `ResponseEventStream.Checkpoint()` only after a workflow superstep supplies a new
checkpoint ID and the matching `AgentSession` save succeeds. `PersistedResponse.Output.Count` is not
the workflow cursor. `_last_checkpoint_id` is the explicit link between the response snapshot and
workflow storage.

### Relationship to durable storage (PR #7649)

Sessions and workflow checkpoints already go through `FoundryAgentSessionStore` /
`FoundryJsonCheckpointStore`. AgentServer separately owns resilient task records, response snapshots,
and SSE event replay. Resilience does not invent another store; it coordinates handler re-entry with
the existing session and workflow stores.

## Consequences

- Samples: `Hosted-Workflow-Resilient`, `Hosted-Workflow-Resilient-Long-Running`, and
  `Hosted-Steering`.
- `Using-E2E-Resilience` runs the complete local crash-recovery demonstration in one console:
  it consumes the server through a MAF agent created by `AIProjectClient`, force-kills the process,
  restarts it, reconnects with a sequence-aware `ResponseContinuationToken`, then uses a third call
  on the same agent and session without a sequence cursor to replay the full stream. It validates
  the exact final countdown against the client accumulator and cursor-free replay.
- Handler-level tests cover recovery input skip, consumption of an available response snapshot,
  response checkpoint deduplication by workflow checkpoint ID, and session-save failure that keeps
  the prior paired boundary.
- A local two-lifetime integration test starts a real Responses host, persists a MAF
  `AgentSession`, stops the host, starts a new host over the same local AgentServer state, and
  verifies that the same response completes without re-injecting the original input.
- A deterministic countdown recovery test interrupts a workflow after outputs `6`, `5`, and `4`,
  starts a new host, and verifies the final output is exactly `6`, `5`, `4`, `3`, `2`, `1`,
  `Countdown complete.` with no missing or duplicated items.
- A local steering integration test sends two real HTTP turns through AgentServer and the MAF
  adapter. It verifies `queued`, serial execution, delivery of the steering input, and reuse of the
  persisted session.
- Live Foundry tests cover background continuation without client traffic, hard process
  termination through `Environment.Exit`, recovery in a different process incarnation, transient
  `404`/`424` polling responses during replacement, and long-running steering on the same
  conversation.
- The checkpoint-index optimistic-concurrency retry count is configurable through
  `FoundryJsonCheckpointStore`, with a default of eight attempts.
- Package floor: Azure.AI.AgentServer Core beta.28, Invocations beta.6, Responses beta.8.
