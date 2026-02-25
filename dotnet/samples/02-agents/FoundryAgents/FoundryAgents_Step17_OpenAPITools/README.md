# Using OpenAPI Tools with AI Agents

This sample demonstrates how to use OpenAPI tools with AI agents. OpenAPI tools allow agents to call external REST APIs defined by OpenAPI specifications.

## What this sample demonstrates

- Creating agents with OpenAPI tool capabilities
- Using AgentTool.CreateOpenApiTool with an embedded OpenAPI specification
- Anonymous authentication for public APIs
- Running an agent that can call external REST APIs
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses `DefaultAzureCredential` for authentication, which supports multiple authentication methods including Azure CLI, managed identity, and more. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure Identity documentation](https://learn.microsoft.com/dotnet/api/azure.identity.defaultazurecredential).

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/02-agents/FoundryAgents
dotnet run --project .\FoundryAgents_Step17_OpenAPITools
```

## Expected behavior

The sample will:

1. Create an agent with an OpenAPI tool configured to call the REST Countries API
2. Ask the agent: "What countries use the Euro (EUR) as their currency?"
3. The agent will use the OpenAPI tool to call the REST Countries API
4. Display the response containing the list of countries that use EUR
5. Clean up resources by deleting the agent