# SharePoint Grounding with the Responses API

This sample shows how to use the SharePoint Grounding tool with a `ChatClientAgent` using the Responses API directly.

## What this sample demonstrates

- Configuring `SharePointGroundingToolOptions` with project connections
- Using `FoundryAITool.CreateSharepointTool()` with `ChatClientAgent`
- Displaying grounding annotations from agent responses

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- An authenticated Azure identity (for example, sign in with `az login`)
- SharePoint connection configured in your Microsoft Foundry project

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
$env:SHAREPOINT_PROJECT_CONNECTION_ID="your-sharepoint-connection-id"  # The full ARM resource URI, e.g., "/subscriptions/.../connections/SharepointTestTool"
```

## Run the sample

```powershell
dotnet run
```

