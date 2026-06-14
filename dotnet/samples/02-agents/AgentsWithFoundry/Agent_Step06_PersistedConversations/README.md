# Persisted Conversations with the Responses API

This sample demonstrates how to persist and resume agent conversations using session serialization.

## What this sample demonstrates

- Serializing agent sessions to JSON for persistence
- Saving and loading sessions from disk
- Resuming conversations with preserved context
- No server-side agent creation or cleanup required

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- An authenticated Azure identity (for example, sign in with `az login`)

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
```

## Run the sample

```powershell
cd dotnet/samples/02-agents/AgentsWithFoundry
dotnet run --project .\Agent_Step06_PersistedConversations
```
