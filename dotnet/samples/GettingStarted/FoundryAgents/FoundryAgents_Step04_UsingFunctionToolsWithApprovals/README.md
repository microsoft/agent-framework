# Using Function Tools with Approvals (Human-in-the-Loop)

This sample demonstrates how to use function tools that require human approval before execution, implementing a human-in-the-loop workflow.

## What this sample demonstrates

- Creating approval-required function tools using ApprovalRequiredAIFunction
- Handling user input requests for function approvals
- Implementing human-in-the-loop approval workflows
- Processing agent responses with pending approvals
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
dotnet run --project .\FoundryAgents_Step04_UsingFunctionToolsWithApprovals
```

## Expected behavior

The sample will:

1. Create an agent named "WeatherAssistant" with an approval-required GetWeather function tool
2. Run the agent with a prompt asking about weather
3. The agent will request approval before invoking the GetWeather function
4. The sample will prompt the user to approve or deny the function call (enter 'Y' to approve)
5. After approval, the function will be executed and the result returned to the agent
6. Clean up resources by deleting the agent

**Note**: For hosted agents with remote users, combine this sample with the Persisted Conversations sample to persist chat history while waiting for user approval.

