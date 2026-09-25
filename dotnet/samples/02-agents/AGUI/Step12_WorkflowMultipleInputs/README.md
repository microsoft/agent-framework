# Multiple Workflow Inputs over AG-UI

This travel-planning workflow requests dates, traveler details, and travel preferences in the same turn.
The client responds to two requests out of order, then submits the remaining preference response in a later
continuation. The workflow produces its final result only after all three inputs are available.

The sample uses an in-memory session store without user isolation for local demonstration only. Production
hosts must isolate persisted sessions by authenticated principal.

## Run

```powershell
dotnet run --project Server --urls http://localhost:8888
dotnet run --project Client
```
