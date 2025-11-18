# Persisted Conversations with AI Agents

This sample demonstrates how to serialize and persist agent conversation threads to storage, allowing conversations to be resumed later.

## What this sample demonstrates

- Serializing agent threads to JSON
- Persisting thread state to disk
- Loading and deserializing thread state from storage
- Resuming conversations with persisted threads
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
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
dotnet run --project .\FoundryAgents_Step06_PersistedConversations
```

## Expected behavior

The sample will:

1. Create an agent named "JokerAgent" with instructions to tell jokes
2. Create a thread and run the agent with an initial prompt
3. Serialize the thread state to JSON
4. Save the serialized thread to a temporary file
5. Load the thread from the file and deserialize it
6. Resume the conversation with the same thread using a follow-up prompt
7. Clean up resources by deleting the agent

