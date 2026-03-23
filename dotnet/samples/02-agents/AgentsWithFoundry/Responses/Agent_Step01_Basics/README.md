# Creating and Running a Basic Agent with the Responses API

This sample demonstrates how to create and run a basic AI agent using the `ChatClientAgent`, which uses the Microsoft Foundry Responses API directly without creating server-side agent definitions.

## What this sample demonstrates

- Creating a `ChatClientAgent` with instructions and a model
- Running a simple single-turn conversation
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
cd dotnet/samples/02-agents/AgentsWithFoundry/Responses
dotnet run --project .\Agent_Step01_Basics
```
