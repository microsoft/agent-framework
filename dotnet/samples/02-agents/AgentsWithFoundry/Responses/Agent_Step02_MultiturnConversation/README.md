# Multi-turn Conversation with the Responses API

This sample demonstrates how to implement multi-turn conversations using the `ChatClientAgent`, where context is preserved across multiple agent runs using sessions.

## What this sample demonstrates

- Creating a `ChatClientAgent` with instructions
- Using sessions to maintain conversation context across multiple runs
- Running multi-turn conversations with text output
- Running multi-turn conversations with streaming output
- No server-side agent creation or cleanup required

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Microsoft Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

## Run the sample

Navigate to the ChatClientAgents sample directory and run:

```powershell
cd dotnet/samples/02-agents/ChatClientAgents
dotnet run --project .\ChatClientAgents_Step02_MultiturnConversation
```
