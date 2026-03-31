# Using Function Tools with the Responses API

This sample demonstrates how to use function tools with the `ChatClientAgent`, allowing the agent to call custom functions to retrieve information.

## What this sample demonstrates

- Creating function tools using `AIFunctionFactory`
- Passing function tools to a `ChatClientAgent`
- Running agents with function tools (text output)
- Running agents with function tools (streaming output)
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

Navigate to the AgentsWithFoundry sample directory and run:

```powershell
cd dotnet/samples/02-agents/AgentsWithFoundry
dotnet run --project .\Agent_Step03_UsingFunctionTools
```
