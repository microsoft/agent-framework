# Issue #5350 — Root-cause validation plan

**Issue:** [`.NET: [Bug]: Checkpoint round-trip loses ToolApprovalRequestContent.ToolCall concrete type (FunctionCallContent → base ToolCallContent), breaking FICC approval resume`](https://github.com/microsoft/agent-framework/issues/5350)

**Status of repro:** A focused repro test class
`dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests/ToolApprovalRequestCheckpointReproTests.cs`
was added covering seven progressively more end-to-end variants of the path the issue
describes — including a **maximal** end-to-end test that uses a real
`ChatClientAgent` driven by `FunctionInvokingChatClient` with an
`ApprovalRequiredAIFunction`. **All seven tests pass** on `main`, consistently across
5 back-to-back runs, i.e. *the bug as described does not reproduce* at any of the
layers exercised here:

| # | Test                                                                                | What it exercises                                                                                                                                                  | Result |
|---|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------|
| 1 | `Repro_5350_ToolApprovalRequestContent_DirectJsonMarshallerRoundtrip_PreservesFunctionCallContent` | `JsonMarshaller.Marshal/Marshal<T>` on `ToolApprovalRequestContent` directly (same options chain as `CheckpointManager.CreateJson`)                                | Pass   |
| 2 | `Repro_5350_ToolApprovalRequestContent_WrappedInPortableValue_PreservesFunctionCallContent`       | Same, wrapped in a `PortableValue` (as `PortableMessageEnvelope` would store it)                                                                                  | Pass   |
| 3 | `Repro_5350_ToolApprovalRequestContent_AsExternalRequestData_PreservesFunctionCallContent`        | Same, as the `Data` payload of an `ExternalRequest`                                                                                                                | Pass   |
| 4 | `Repro_5350_DirectJsonMarshallerRoundtrip_IsDeterministic`                          | 25× repetition of #1 to rule out flakiness / JIT order                                                                                                             | Pass   |
| 5 | `Repro_5350_CaptureWireFormat_ForInspection`                                        | Captures the on-the-wire shape so we can compare against the OP's SQL row                                                                                          | Pass   |
| 6 | `Repro_5350_EndToEnd_JsonCheckpointResume_PreservesFunctionCallContentAsync`        | Full `CheckpointManager.CreateJson(InMemoryJsonStore) → RunStreamingAsync → SuperStep checkpoint → ResumeStreamingAsync` cycle with a `RequestPort<TARC, TARR>`    | Pass   |
| 7 | `Repro_5350_EndToEnd_ChatClientAgent_WithApprovalRequiredTool_JsonCheckpointResume_PreservesFunctionCallContentAndInvokesToolAsync` | **Maximal**: `ChatClientAgent` over a `MockChatClient` with an `ApprovalRequiredAIFunction`, single-agent `WorkflowBuilder` (no orchestration), `CheckpointManager.CreateJson(InMemoryJsonStore)`. Asserts both that the resumed `RequestInfoEvent.Request` still carries a `FunctionCallContent` AND that approving the request actually invokes the underlying `AIFunction` and lets the workflow continue. | Pass   |

This is **consistent with [@lokitoth's second comment](https://github.com/microsoft/agent-framework/issues/5350#issuecomment-4379664401)**:

> Looking at the MEAI types, it does have `[JsonDerivedType(typeof(FunctionCallContent), "functionCall")]` set on it, and has had it that way for some time, so it is unlikely to be the root cause. […] `JsonMarshaller` […] takes an optional `JsonSerializationOptions` provided by the user […] but this is used only if the internal one (via `WorkflowsJsonUtilities`, which chains to `AgentAbstractionsJsonUtilities`, which then chains to the `AIJsonUtilities` class) [is missing the type].

Inspection of the actual wire format produced by `JsonMarshaller` for a
`ToolApprovalRequestContent` containing a `FunctionCallContent` confirms the
discriminator is emitted:

```jsonc
// TARC at top level
{
  "toolCall": {
    "$type": "functionCall",      // ← polymorphism discriminator present
    "name": "DoTheThing",
    "arguments": { "x": 42 },
    "informationalOnly": false,
    "callId": "call-1"
  },
  "requestId": "req-1"
}

// TARC inside a PortableValue (= shape stored by PortableMessageEnvelope)
{
  "typeId": {
    "assemblyName": "Microsoft.Extensions.AI.Abstractions, Version=10.5.0.0, …",
    "typeName": "Microsoft.Extensions.AI.ToolApprovalRequestContent"
  },
  "value": {
    "toolCall": {
      "$type": "functionCall",
      …
    },
    "requestId": "req-1"
  }
}
```

So the OP's stated root-cause hypothesis — *"`AIContent`/`ToolCallContent`/
`FunctionCallContent` are missing `[JsonPolymorphic]`/`[JsonDerivedType]`, or
`CheckpointManager.CreateJson` does not pull from `AIJsonUtilities.DefaultOptions`"*
— is **not** what is producing the failure described in the issue. The annotations
exist, the resolver chain wires them through, and the discriminator does survive
both the direct `JsonMarshaller` round-trip and a real `Run → checkpoint → Resume`
cycle for a `RequestPort` whose request type is `ToolApprovalRequestContent`.

The remaining sections lay out, in priority order, the work needed to identify
the *actual* root cause. The plan deliberately keeps the failing repro from
above as the baseline ("this is what works") and walks outward from it toward
the OP's reported scenario, varying one dimension at a time.

## Plan

### Track A — Reproduce in a configuration closer to the OP's pattern "B"

The OP's repro path differs from the new tests in three concrete ways. Tests #7
(maximal repro) and #8–#10 (A2 / A3 / A4 below) close all four gaps. The OP's
specific hypothesis (`TARC.ToolCall is not FunctionCallContent` after resume) does
not reproduce in any of them; A2 did however uncover a *separate, unrelated* bug.

| Step | Variable that changes vs. the passing tests in this repo                                                                                              | Why it matters                                                                                                                                                                                                       | Outcome                                                                |
|------|--------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| A1   | ~~Use `ChatClientAgent` + `ApprovalRequiredAIFunction` bound into a `WorkflowBuilder`~~ — **covered by test #7 in this PR; passes.**                  | Was the largest gap to the OP's repro. Closed.                                                                                                                                                                       | OP hypothesis disproved — `TARC.ToolCall is FunctionCallContent` post-resume, and the tool is actually invoked exactly once when the approval response is sent. |
| A2   | Multi-agent variant: same as #7 but with the agent inside a `GroupChatBuilder` (the OP's actual orchestration) with `RoundRobinGroupChatManager`.     | If group chat re-encodes TARC as part of `ChatMessage.Contents` (`AIContent` polymorphism is two-deep through `ToolApprovalRequestContent`), one branch may resolve and the other not.                              | OP hypothesis disproved — `TARC.ToolCall is FunctionCallContent` post-resume. **But:** sending the approval response surfaces a *different* real bug — `FunctionInvokingChatClient.ExtractAndRemoveApprovalRequestsAndResponses` throws `ArgumentException: An item with the same key has already been added. Key: ficc_call-1`. Pinned by test as documented misbehavior. |
| A2b  | Same as A2 but using `HandoffWorkflowBuilder` (initial agent has the approval tool, a no-op peer agent makes the handoff graph valid; the mock chat client never emits a `handoff_to_*` call). | If the duplicate-key bug from A2 is broader than `RoundRobinGroupChatManager` and lives in the shared `AIAgentHostExecutor` / `ChatProtocolExecutor` path, the handoff workflow should hit it too. | OP hypothesis disproved — `TARC.ToolCall is FunctionCallContent` post-resume **and** the workflow completes cleanly: tool invoked exactly once, zero errors, zero executor failures. The duplicate-key bug from A2 does **not** occur on the handoff path, narrowing it to the group-chat-specific orchestration. |
| A3   | Same as #7 but with the checkpoint `JsonElement` round-tripped through `string` + `JsonDocument.Parse` between commit and retrieve (`StringRoundTripJsonStore`), emulating the SQL `nvarchar` hop in the OP's Dapper store.                                                                                | The OP uses Dapper + SQL Server. If the column / driver round-trip preserves ordering, this should be identity-preserving — but if it reorders metadata properties, the `$type` discriminator can be moved out of first position, which then requires `AllowOutOfOrderMetadataProperties = true`. | OP hypothesis disproved — byte-preserving string round-trip is identity-preserving for the relevant payload; `TARC.ToolCall is FunctionCallContent` post-resume; tool invoked exactly once. The OP's storage layer would have to *perturb* the JSON (e.g. reorder metadata) for this to reproduce. |
| A4   | Same as #7 but with non-default `JsonSerializerOptions` (`JsonSerializerDefaults.Web`, no AIJsonUtilities resolver) passed as `customOptions` to `CheckpointManager.CreateJson`.                                                                                                                          | `JsonMarshaller.LookupTypeInfo` only goes to the external options when the internal chain doesn't know about the type. For most cases this won't trigger, but it's worth confirming that supplying a custom `JsonSerializerOptions` does not silently displace the internal chain.                            | OP hypothesis disproved — custom external options that DO NOT know about `AIContent` types are correctly ignored for known types; the internal `WorkflowsJsonUtilities.DefaultOptions` chain wins. `TARC.ToolCall is FunctionCallContent` post-resume; tool invoked exactly once. |

### Track B — Validate the wire format the OP actually persists

Once Track A has reproduced (or has clearly failed to reproduce) the symptom,
ask the OP for one of the following, in order of preference:

1. The raw `JsonElement.GetRawText()` they pass to their SQL store on commit,
   and the raw string they read back on `RetrieveCheckpointAsync` — for the
   exact checkpoint that contains the failing `ToolApprovalRequestContent`.
   This tells us in a single round-trip whether:
   - the `$type` discriminator is present on commit (rules out write-side bug),
   - the `$type` discriminator survives the SQL round-trip (rules out store bug),
   - the discriminator is in metadata-first position (rules out the
     `AllowOutOfOrderMetadataProperties` story).
2. A repro PR/gist that runs against `CheckpointManager.CreateJson(...)` with
   an in-memory `JsonCheckpointStore` shim that mirrors how their SQL subclass
   passes bytes through. The OP already offered this in the issue body
   (*"I can produce a minimal standalone repro against a fake `IChatClient` if useful — let me know."*) — taking them up on it short-circuits a lot of guessing.

### Track C — Defense-in-depth fixes worth landing regardless of root cause

These are addressed in the OP's "Asks" section (asks 2–4) and are useful
documentation/ergonomics improvements even if the root cause turns out to be in
the OP's store implementation:

1. **Doc-only**: in the XML docs for `CheckpointManager.CreateJson` and on the
   `JsonCheckpointStore` base class, explicitly state that the internal options
   chain through `WorkflowsJsonUtilities → AgentAbstractionsJsonUtilities →
   AIJsonUtilities`, and that user-supplied `customOptions` are consulted only
   when the internal chain has no `TypeInfo` for a requested type.
2. **Doc-only**: document the contract that any user `JsonCheckpointStore`
   subclass MUST preserve the exact byte sequence of the `JsonElement` it is
   given. If the underlying store reorders JSON metadata, the consumer must opt
   in by setting `AllowOutOfOrderMetadataProperties = true` on a
   `JsonSerializerOptions` passed as `customOptions` to
   `CheckpointManager.CreateJson(...)`.
3. **Optional, only if Track A reproduces**: add a regression test mirroring
   the failing path under `dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests`
   so the fix is locked in.

### Track D — Reject the OP's hypothesis (if not already done)

The combination of:

- the polymorphism annotations existing in `Microsoft.Extensions.AI` for some time
  (per @lokitoth),
- the resolver chain in `WorkflowsJsonUtilities.CreateDefaultOptions()` already
  putting `AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver` first
  (which itself puts `AIJsonUtilities.DefaultOptions.TypeInfoResolver` first),
- the wire format captured above showing `"$type": "functionCall"` is present,
- the full `Run → checkpoint → Resume` test in this PR passing for a plain
  `RequestPort<TARC, ToolApprovalResponseContent>` workflow, **and**
- the maximal `ChatClientAgent` + `FunctionInvokingChatClient` +
  `ApprovalRequiredAIFunction` test in this PR also passing — including the
  assertion that the wrapped `AIFunction` is actually invoked exactly once after
  approval and that the workflow then receives the resulting
  `FunctionResultContent` and produces a final assistant message,

is sufficient to **disprove** the OP's stated hypothesis. Once Track A or
Track B identifies the actual cause, the issue should be updated with a brief
explanation of why the original guess was incorrect, so future readers don't
re-tread it.

## Pointers for the next investigator

- Repro tests:
  `dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests/ToolApprovalRequestCheckpointReproTests.cs`
- Marshaller under test:
  `dotnet/src/Microsoft.Agents.AI.Workflows/Checkpointing/JsonMarshaller.cs`
- Where `CheckpointManager.CreateJson` enters that path:
  `dotnet/src/Microsoft.Agents.AI.Workflows/CheckpointManager.cs`
- Options chain (TARC ⇒ resolver):
  `dotnet/src/Microsoft.Agents.AI.Workflows/WorkflowsJsonUtilities.cs`
  → `dotnet/src/Microsoft.Agents.AI.Abstractions/AgentAbstractionsJsonUtilities.cs`
  → `Microsoft.Extensions.AI.AIJsonUtilities.DefaultOptions`
- `PortableValue`-side serialization (this is where `value.Value.GetType()` is
  used on write, which is the most plausible *internal* place a polymorphism
  bug could hide, but the wire capture above shows it is not the cause in the
  TARC-as-RequestPort scenario):
  `dotnet/src/Microsoft.Agents.AI.Workflows/Checkpointing/PortableValueConverter.cs`
- Likely next code to inspect for Track A1/A2 (agent-host serialization path):
  `dotnet/src/Microsoft.Agents.AI.Workflows/AIAgentHostExecutor*.cs` and
  whatever turns the FICC-generated TARC into something
  `AIAgentHostExecutor` stores in its state bag.
