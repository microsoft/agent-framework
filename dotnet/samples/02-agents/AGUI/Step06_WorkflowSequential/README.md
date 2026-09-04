# Sequential Workflow over AG-UI

This sample hosts a two-agent sequential workflow over AG-UI. The `Writer` drafts a response and the
`Reviewer` produces the final answer. The client prints AG-UI step lifecycle events alongside streamed text.

## Run

Set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT_NAME`, then:

```powershell
dotnet run --project Server --urls http://localhost:8888
dotnet run --project Client
```

Expected step events include `STEP_STARTED` and `STEP_FINISHED` for `Writer` followed by `Reviewer`.
