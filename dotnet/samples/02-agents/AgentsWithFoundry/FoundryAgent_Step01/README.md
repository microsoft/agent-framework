# FoundryAgent Step 01 - Direct Construction

This sample demonstrates how to create a `FoundryAgent` directly using a project endpoint and credentials, without manually constructing an `AIProjectClient`.

## Prerequisites

- An Azure AI Foundry project endpoint
- A model deployment name (defaults to `gpt-4o-mini`)

## Environment Variables

| Variable | Description | Required |
| --- | --- | --- |
| `AZURE_AI_PROJECT_ENDPOINT` | Azure AI Foundry project endpoint | Yes |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment name | No (defaults to `gpt-4o-mini`) |

## Running the sample

```powershell
cd dotnet/samples/02-agents/AgentsWithFoundry
dotnet run --project .\FoundryAgent_Step01
```
