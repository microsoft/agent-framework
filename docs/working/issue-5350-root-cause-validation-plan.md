# Issue #5350 — Root-cause validation plan

**Issue:** [`.NET: [Bug]: Checkpoint round-trip loses ToolApprovalRequestContent.ToolCall concrete type (FunctionCallContent → base ToolCallContent), breaking FICC approval resume`](https://github.com/microsoft/agent-framework/issues/5350)

**Status of repro:** A focused repro test class
`dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests/ToolApprovalRequestCheckpointReproTests.cs`
was added covering six progressively more end-to-end variants of the path the issue
describes. **All six tests pass** on `main`, i.e. *the bug as described does not
reproduce* at any of the layers exercised here:

| # | Test                                                                                | What it exercises                                                                                                                                                  | Result |
|---|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------|
| 1 | `Repro_5350_ToolApprovalRequestContent_DirectJsonMarshallerRoundtrip_PreservesFunctionCallContent` | `JsonMarshaller.Marshal/Marshal<T>` on `ToolApprovalRequestContent` directly (same options chain as `CheckpointManager.CreateJson`)                                | Pass   |
| 2 | `Repro_5350_ToolApprovalRequestContent_WrappedInPortableValue_PreservesFunctionCallContent`       | Same, wrapped in a `PortableValue` (as `PortableMessageEnvelope` would store it)                                                                                  | Pass   |
| 3 | `Repro_5350_ToolApprovalRequestContent_AsExternalRequestData_PreservesFunctionCallContent`        | Same, as the `Data` payload of an `ExternalRequest`                                                                                                                | Pass   |
| 4 | `Repro_5350_DirectJsonMarshallerRoundtrip_IsDeterministic`                          | 25× repetition of #1 to rule out flakiness / JIT order                                                                                                             | Pass   |
| 5 | `Repro_5350_CaptureWireFormat_ForInspection`                                        | Captures the on-the-wire shape so we can compare against the OP's SQL row                                                                                          | Pass   |
| 6 | `Repro_5350_EndToEnd_JsonCheckpointResume_PreservesFunctionCallContentAsync`        | Full `CheckpointManager.CreateJson(InMemoryJsonStore) → RunStreamingAsync → SuperStep checkpoint → ResumeStreamingAsync` cycle with a `RequestPort<TARC, TARR>`    | Pass   |

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

The OP's repro path differs from the new tests in three concrete ways. Each is a
candidate root cause; the test matrix below isolates them. Each row is "add a
test that reproduces the OP's symptom (`postResume.ToolCall is not FunctionCallContent`)".

| Step | Variable that changes vs. the passing tests in this repo                                                                                              | Why it matters                                                                                                                                                                                                       | Pass criteria                                                                |
|------|--------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| A1   | Use `ChatClientAgent` + `ApprovalRequiredAIFunction` bound into a `WorkflowBuilder` (the GroupChatToolApproval "pattern B" path), with a fake `IChatClient` that emits a single `FunctionCallContent`. | This is the only major piece of the OP's setup that the current tests do not exercise. The TARC in this path is *generated* by `FunctionInvokingChatClient` and flows through the `AIAgentHostExecutor`. | Test fails (TARC.ToolCall comes back as base type) → root cause is in the agent-host/FICC bridge, not the marshaller. |
| A2   | Same as A1 but with the request payload also surfaced as part of a `ChatMessage.Contents`-style transport (whatever the agent host actually serializes through). Inspect the on-the-wire JSON for the inner `toolCall` and look for an absent or differently-named `$type`. | If the TARC is round-tripped as `AIContent`/`ChatMessage` instead of as itself, the polymorphism is two-deep (`AIContent` → TARC, TARC → ToolCall). It is plausible that one branch resolves but the other doesn't.  | Find missing `$type` in serialized payload.                                  |
| A3   | Same as the passing test #6 in this file, but with the SQL Server-style store that round-trips the `JsonElement` through `string` and back (e.g. `element.GetRawText()` → `JsonDocument.Parse`).                                                                                                              | The OP uses Dapper + SQL Server. If the column is `nvarchar` and the round-trip preserves ordering, this should be identity-preserving — but if the OP uses `jsonb`-like storage that reorders metadata properties, the `$type` discriminator can be moved out of "first" position, which then requires `AllowOutOfOrderMetadataProperties = true`. Note `JsonMarshaller` only propagates that one flag from the user's `customOptions`. | Test fails when ordering is permuted before deserialization. Confirms the storage layer is reordering metadata. |
| A4   | Same as #6 but with a non-default `JsonSerializerOptions` passed as `customOptions` to `CheckpointManager.CreateJson`, where the user-supplied options do **not** include the polymorphism resolver and `JsonMarshaller`'s `LookupTypeInfo` falls back to them for some type. | `JsonMarshaller.LookupTypeInfo` only goes to the external options when the internal chain doesn't know about the type. For most cases this won't trigger, but it's worth confirming that supplying a custom `JsonSerializerOptions` does not silently displace the internal chain.                            | Either the external options are never consulted for `AIContent` (good), or there is a sneak path where they are (regression).                                                                                                  |

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
- the wire format captured above showing `"$type": "functionCall"` is present, and
- the full `Run → checkpoint → Resume` test in this PR passing,

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
