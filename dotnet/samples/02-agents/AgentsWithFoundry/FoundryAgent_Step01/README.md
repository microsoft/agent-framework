# FoundryAgent Step 01 - Server-Side Agent Lifecycle

This sample demonstrates the full lifecycle of a `FoundryAgent` backed by a server-side versioned agent in Azure AI Foundry: create → run → delete.

## Prerequisites

- An Azure AI Foundry project endpoint
- A model deployment name (defaults to `gpt-4o-mini`)
- Azure CLI installed and authenticated

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
