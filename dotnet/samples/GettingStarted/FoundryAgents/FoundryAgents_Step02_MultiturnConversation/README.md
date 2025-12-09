# Multi-turn Conversation with AI Agents

This sample demonstrates how to implement multi-turn conversations with AI agents, where context is preserved across multiple agent runs using threads.

## What this sample demonstrates

- Creating an AI agent with instructions
- Using threads to maintain conversation context
- Running multi-turn conversations with text output
- Running multi-turn conversations with streaming output
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/GettingStarted/FoundryAgents
dotnet run --project .\FoundryAgents_Step02_MultiturnConversation
```

## Expected behavior

The sample will:

1. Create an agent named "JokerAgent" with instructions to tell jokes
2. Create a thread for conversation context
3. Run the agent with a text prompt and display the response
4. Send a follow-up message to the same thread, demonstrating context preservation
5. Create a new thread and run the agent with streaming
6. Send a follow-up streaming message to demonstrate multi-turn streaming
7. Clean up resources by deleting the agent

