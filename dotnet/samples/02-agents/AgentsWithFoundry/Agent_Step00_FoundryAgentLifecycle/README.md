# Agent Step 00 - FoundryAgent Lifecycle

This sample demonstrates the full lifecycle of a `FoundryAgent` backed by a server-side versioned agent in Microsoft Foundry: create → run → delete.

## Prerequisites

- A Microsoft Foundry project endpoint
- A model deployment name (defaults to `gpt-5.4-mini`)
- An authenticated Azure identity (for example, sign in with `az login`)

## Environment Variables

| Variable | Description | Required |
| --- | --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Microsoft Foundry project endpoint | Yes |
| `FOUNDRY_MODEL` | Model deployment name | No (defaults to `gpt-5.4-mini`) |

## Running the sample

```powershell
cd dotnet/samples/02-agents/AgentsWithFoundry
dotnet run --project .\Agent_Step00_FoundryAgentLifecycle
```
