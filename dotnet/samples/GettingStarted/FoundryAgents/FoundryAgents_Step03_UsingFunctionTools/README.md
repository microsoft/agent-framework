# Using Function Tools with AI Agents

This sample demonstrates how to use function tools with AI agents, allowing agents to call custom functions to retrieve information.

## What this sample demonstrates

- Creating function tools using AIFunctionFactory
- Passing function tools to an AI agent
- Running agents with function tools (text output)
- Running agents with function tools (streaming output)
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
dotnet run --project .\FoundryAgents_Step03.1_UsingFunctionTools
```

## Expected behavior

The sample will:

1. Create an agent named "WeatherAssistant" with a GetWeather function tool
2. Run the agent with a text prompt asking about weather
3. The agent will invoke the GetWeather function tool to retrieve weather information
4. Run the agent again with streaming to display the response as it's generated
5. Clean up resources by deleting the agent

