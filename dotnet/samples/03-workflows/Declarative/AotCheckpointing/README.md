# AotCheckpointing sample

Demonstrates JSON checkpointing of a declarative workflow under
reflection-disabled `System.Text.Json` -- the same constraint imposed by
**AOT / trim-aggressive deployments**.

## What it shows

- A 3-action declarative workflow
  (`SetVariable` -> `InvokeAzureAgent` -> `SendActivity`) checkpointed
  after every superstep.
- The csproj sets
  `<JsonSerializerIsReflectionEnabledByDefault>false</JsonSerializerIsReflectionEnabledByDefault>`.
  Every JSON operation must resolve type info via a source-gen
  `JsonSerializerContext` or fail with
  `InvalidOperationException: No JSON type info is available for type 'X'`.
- The experimental
  [`DeclarativeWorkflowJsonOptions.Default`](../../../../src/Microsoft.Agents.AI.Workflows.Declarative/DeclarativeWorkflowJsonOptions.cs)
  `JsonSerializerOptions` instance covers every declarative-package
  type that flows through the checkpoint pipeline. Pass it to
  `CheckpointManager.CreateJson`.
- JSON round-trip is verified in two phases:
  1. Run + drain -- every `[checkpoint x<n>]` line is a successful JSON **write**.
  2. `ResumeStreamingAsync` on a fresh workflow instance -- a clean
     return is the proof JSON **reads** round-trip too. The resumed run
     is disposed immediately; without a pending external request it
     would park in `WaitForInputAsync` indefinitely.

`DeclarativeWorkflowJsonOptions` is marked
`[Experimental("MAAI001")]`. Suppress that diagnostic in your csproj to
use it.

### Registering user-defined types

For workflows whose inputs or custom `ActionExecutorResult.Result`
payloads are user-defined, clone `Default` and append your own resolver:

```csharp
JsonSerializerOptions options = new(DeclarativeWorkflowJsonOptions.Default);
options.TypeInfoResolverChain.Add(MyAppJsonContext.Default);
options.MakeReadOnly();
CheckpointManager manager = CheckpointManager.CreateJson(store, options);
```

## Run

Prerequisites:

- Azure Foundry project with a deployed model.
- `az login`.
- Configuration (user secrets or env):

  | Setting | Description |
  | --- | --- |
  | `AZURE_AI_PROJECT_ENDPOINT` | Foundry project endpoint URL. |
  | `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment name. |

  See the [parent README](../README.md) for the full walkthrough.

```sh
cd dotnet/samples/03-workflows/Declarative/AotCheckpointing
dotnet run "Hello, my name is Ada."
```

Expected output:

1. `[checkpoint x<n>]` lines after each superstep.
2. The agent's streamed response.
3. `ACTIVITY: [Sample] Workflow completed. ...`
4. `WORKFLOW: Verifying read path by resuming from checkpoint <id>`
5. `WORKFLOW: Checkpoint deserialized successfully`
6. `WORKFLOW: Done!`

The `chk-*/` checkpoint folder is deleted at the end.

## Observe the failure mode

Drop the options argument:

```csharp
CheckpointManager checkpointManager = CheckpointManager.CreateJson(store, DeclarativeWorkflowJsonOptions.Default);
```

becomes

```csharp
CheckpointManager checkpointManager = CheckpointManager.CreateJson(store);
```

Clean rebuild, then re-run. Expected on the first checkpoint commit:

```
System.InvalidOperationException: No JSON type info is available for type
'Microsoft.Agents.AI.Workflows.Declarative.Kit.ActionExecutorResult'.
```

This is what `dotnet publish -p:PublishAot=true` would surface at runtime.

## Notes

- `PublishAot=true` is **not** set. The
  `JsonSerializerIsReflectionEnabledByDefault=false` flag is the
  minimum constraint that reproduces the AOT failure for JSON
  checkpointing.
- JSON code paths inside transitive dependencies (e.g. Foundry SDK)
  that rely on reflection would also fail under this flag; those are
  outside the workflow framework's responsibility.
