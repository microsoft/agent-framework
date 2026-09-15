# Tool-enabled Workflow over AG-UI

This sample hosts a workflow containing an agent with a backend weather tool. Executor steps, tool calls,
tool results, and text all travel through the same AG-UI stream.

## Run

Set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT_NAME`, then:

```powershell
dotnet run --project Server --urls http://localhost:8888
dotnet run --project Client
```
