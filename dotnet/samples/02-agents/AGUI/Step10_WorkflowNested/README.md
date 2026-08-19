# Parallel Nested Workflows over AG-UI

This sample runs `SecurityPipeline` and `StylePipeline` as parallel subworkflows. Each subworkflow contains
a locally scoped executor named `Analyze`.

The client currently receives duplicate `Analyze_Analyze` step names because nested executor lifecycle events
do not carry their parent workflow scope. AG-UI rejects the second overlapping `STEP_STARTED` as already active.
The client reports this known limitation, which is tracked by issue #7763.

## Run

```powershell
dotnet run --project Server --urls http://localhost:8888
dotnet run --project Client
```
