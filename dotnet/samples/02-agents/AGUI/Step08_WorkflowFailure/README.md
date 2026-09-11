# Failing Workflow over AG-UI

This sample demonstrates an executor failure. The AG-UI stream emits `STEP_FINISHED` for the failed executor
and then terminates with `RUN_ERROR`; it does not append a successful `RUN_FINISHED`.

## Run

```powershell
dotnet run --project Server --urls http://localhost:8888
dotnet run --project Client
```
