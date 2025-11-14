# Dependency Injection with AI Agents

This sample demonstrates how to use dependency injection to register and manage AI agents within a hosted service application.

## What this sample demonstrates

- Setting up dependency injection with HostApplicationBuilder
- Registering AIProjectClient as a singleton service
- Registering AIAgent as a singleton service
- Using agents in hosted services
- Interactive chat loop with streaming responses
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
dotnet run --project .\FoundryAgents_Step08_DependencyInjection
```

## Expected behavior

The sample will:

1. Create a host with dependency injection configured
2. Register AIProjectClient and AIAgent as services
3. Create an agent named "JokerAgent" with instructions to tell jokes
4. Start an interactive chat loop where you can ask the agent questions
5. The agent will respond with streaming output
6. Enter an empty line or press Ctrl+C to exit
7. Clean up resources by deleting the agent

