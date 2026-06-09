# Multi-turn Conversation

This sample demonstrates how to implement multi-turn conversations where context is preserved across multiple agent runs using sessions and response ID chaining.

## What this sample demonstrates

- Creating an agent with instructions
- Using sessions to maintain conversation context across multiple runs
- Response ID chaining for multi-turn conversations
- No server-side conversation creation required

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- An authenticated Azure identity (for example, sign in with `az login`)

**Note**: This sample uses `DefaultAzureCredential`. `az login` is the easiest local development path, but Visual Studio, VS Code, and managed identity credentials also work when available.

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
```

## Run the sample

Navigate to the AgentsWithFoundry sample directory and run:

```powershell
cd dotnet/samples/02-agents/AgentsWithFoundry
dotnet run --project .\Agent_Step02.1_MultiturnConversation
```
