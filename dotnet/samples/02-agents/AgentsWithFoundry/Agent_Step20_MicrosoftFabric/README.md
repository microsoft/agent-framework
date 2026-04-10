# Microsoft Fabric with the Responses API

This sample shows how to use the Microsoft Fabric tool with a `ChatClientAgent` using the Responses API directly.

## What this sample demonstrates

- Configuring `FabricDataAgentToolOptions` with project connections
- Using `FoundryAITool.CreateMicrosoftFabricTool()` with `ChatClientAgent`
- Querying data available through a Fabric connection

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)
- Microsoft Fabric connection configured in your Microsoft Foundry project

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
$env:FABRIC_PROJECT_CONNECTION_ID="your-fabric-connection-id"  # The full ARM resource URI, e.g., "/subscriptions/.../connections/FabricTestTool"
```

## Run the sample

```powershell
dotnet run
```
