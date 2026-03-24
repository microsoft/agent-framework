# OpenAPI Tools with the Responses API

This sample shows how to use OpenAPI tools with a `ChatClientAgent` using the Responses API directly.

## What this sample demonstrates

- Defining an OpenAPI specification inline
- Creating an `OpenAPIFunctionDefinition` for the REST Countries API
- Using `FoundryAITool.CreateOpenApiTool()` with `ChatClientAgent`
- Server-side execution of OpenAPI tool calls

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

## Run the sample

```powershell
dotnet run
```
