# Getting started with Model Content Protocol

The getting started with Model Content Protocol samples demonstrate how to use MCP Server tools from an agent.

## Getting started with agents prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10.0 SDK or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource.

**Note**: These samples use Azure OpenAI models. For more information, see [how to deploy Azure OpenAI models with Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/deploy-models-openai).

**Note**: These samples use Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource and have the `Cognitive Services OpenAI Contributor` role. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Samples

|Sample|Description|
|---|---|
|[Agent with MCP server tools](./Agent_MCP_Server/)|This sample demonstrates how to use MCP server tools with a simple agent|
|[Agent with MCP server tools and authorization](./Agent_MCP_Server_Auth/)|This sample demonstrates how to use MCP Server tools from a protected MCP server with a simple agent|
|[Responses Agent with Hosted MCP tool](./ResponseAgent_Hosted_MCP/)|This sample demonstrates how to use the Hosted MCP tool with the Responses Service, where the service invokes any MCP tools directly|

## Running the samples from the console

To run the samples, navigate to the desired sample directory, e.g.

```powershell
cd Agents_Step01_Running
```

Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" # Replace with your Azure OpenAI resource endpoint
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

If the variables are not set, you will be prompted for the values when running the samples.

Execute the following command to build the sample:

```powershell
dotnet build
```

Execute the following command to run the sample:

```powershell
dotnet run --no-build
```

Or just build and run in one step:

```powershell
dotnet run
```

## Running the samples from Visual Studio

Open the solution in Visual Studio and set the desired sample project as the startup project. Then, run the project using the built-in debugger or by pressing `F5`.

You will be prompted for any required environment variables if they are not already set.
