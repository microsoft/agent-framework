# Concurrent Workflow over AG-UI

This sample runs a `Researcher` and `Critic` concurrently. The AG-UI client displays each executor's
step lifecycle and the output from both agents.

## Run

Set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT_NAME`, then:

```powershell
dotnet run --project Server --urls http://localhost:8888
dotnet run --project Client
```
