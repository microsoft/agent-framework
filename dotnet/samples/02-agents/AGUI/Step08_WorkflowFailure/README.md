# Failing Workflow over AG-UI

This sample demonstrates an executor failure. The AG-UI stream still emits `STEP_FINISHED` for the failed
executor so clients do not leave the step active.

## Run

```powershell
dotnet run --project Server --urls http://localhost:8888
dotnet run --project Client
```
