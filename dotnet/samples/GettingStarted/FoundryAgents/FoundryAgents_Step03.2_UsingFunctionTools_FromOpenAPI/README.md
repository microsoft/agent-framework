# Using Function Tools from OpenAPI Specifications

This sample demonstrates how to create function tools from an OpenAPI specification and use them with AI agents.

## What this sample demonstrates

- Loading OpenAPI specifications from files
- Converting OpenAPI specifications to Semantic Kernel plugins
- Converting Semantic Kernel plugins to AI function tools
- Using OpenAPI-based function tools with AI agents
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
dotnet run --project .\FoundryAgents_Step03.2_UsingFunctionTools_FromOpenAPI
```

## Expected behavior

The sample will:

1. Load the OpenAPI specification from OpenAPISpec.json (GitHub API)
2. Convert the OpenAPI spec to Semantic Kernel plugins
3. Create an agent named "GitHubAssistant" with the OpenAPI-based function tools
4. Run the agent with a prompt to query GitHub repositories
5. The agent will invoke the appropriate OpenAPI function tools to retrieve data
6. Clean up resources by deleting the agent

