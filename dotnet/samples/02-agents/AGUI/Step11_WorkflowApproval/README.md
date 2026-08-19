# Approval Workflow over AG-UI

This sample pauses a workflow for approval before submitting an expense. The AG-UI client reads the
interruption from `RUN_FINISHED`, asks the user for a decision, and resumes the same workflow thread.

The sample uses an in-memory session store without user isolation for local demonstration only. Production
hosts must isolate persisted sessions by authenticated principal.

## Run

```powershell
dotnet run --project Server --urls http://localhost:8888
dotnet run --project Client
```
