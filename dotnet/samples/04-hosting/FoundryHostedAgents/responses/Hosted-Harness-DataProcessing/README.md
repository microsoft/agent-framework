# Hosted Harness Data Processing

This sample hosts a `HarnessAgent` that reads a sample sales CSV and writes requested reports. It reuses `dotnet/samples/02-agents/Harness/Harness_Step03_DataProcessing/working/sales.csv`. File reads are auto-approved; writes still require an explicit approval that can resume on a later hosted turn.

The project references the framework **source in this repository**. `AddFoundryResponses(agent)` uses the default `AllowStoredOutputEnabled = false`; the agent keeps chat history in its session rather than in the model service.

## Run locally

1. Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` for an existing Foundry model deployment, then sign in with `az login`. Copy `.env.example` to `.env` if you prefer a local file.
2. From this directory, run `dotnet run --tl:off`, then call `POST http://localhost:8088/responses` with model `hosted-harness-data-processing` and a question such as "Which region sold the most units in sales.csv?".
3. Send another request with the same conversation ID. To exercise approval, ask for a written report. The response contains an `mcp_approval_request`; send an `mcp_approval_response` with its ID in the **same conversation and hosted session**. Do not auto-approve writes. `azd ai agent invoke -f` does not send a structured Responses body; use authenticated `az rest --resource https://ai.azure.com` for the approval response.

Hosted containers have a read-only application directory. On startup the sample copies **only missing** seed files into the session's writable home directory so edited files and generated reports survive later turns.

These files rely on Foundry's session sandbox: by default each caller gets their own session with a private `$HOME` (see [Isolate hosted agent sessions per user](https://learn.microsoft.com/azure/foundry/agents/how-to/isolate-sessions-per-user)). If you [place several users in one session](https://learn.microsoft.com/azure/foundry/agents/how-to/multiplex-session-users), partition the working folder per user yourself.

## Container build from this checkout

The project links its CSV from elsewhere in the MAF checkout, so publish from the repository before building this runtime image. Uploading this directory alone as Foundry source/ZIP is not supported:

```powershell
dotnet publish HostedHarnessDataProcessing.csproj -c Release -f net10.0 -r linux-musl-x64 --self-contained false -o out --tl:off
docker build -t hosted-harness-data-processing .
```

The image includes the local framework assemblies. Rebuild it after a framework change rather than testing an older published package.

For deployment to an existing Foundry project, follow the [persistent `azd` container workflow](../Hosted-Harness-Research/README.md#deploy-with-an-existing-foundry-project) with this project's publish output, bundle directory `src\hosted-harness-data`, and agent name `maf-harness-data`. A live hosted validation read the bundled CSV, recalled the answer on a second turn, requested approval before writing, and read the approved file on a later turn. The host kept `AllowStoredOutputEnabled = false`.
