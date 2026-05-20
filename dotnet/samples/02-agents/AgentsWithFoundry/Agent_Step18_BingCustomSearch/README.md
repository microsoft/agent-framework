# Bing Custom Search with the Responses API

This sample shows how to use the Bing Custom Search tool with a `ChatClientAgent` using the Responses API directly.

## What this sample demonstrates

- Configuring `BingCustomSearchToolParameters` with connection ID and instance name
- Using `FoundryAITool.CreateBingCustomSearchTool()` with `ChatClientAgent`
- Processing search results from agent responses

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)
- Bing Custom Search resource configured with a connection ID

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
$env:AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID="your-connection-id"  # The full ARM resource URI, e.g., "/subscriptions/.../connections/your-bing-connection"
$env:AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME="your-instance-name"  # The Bing Custom Search configuration name (from Azure portal)
```

### Finding the connection ID and instance name

- **Connection ID** (`AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID`): The full ARM resource URI including the `/projects/<name>/connections/<connection-name>` segment. Find the connection name in your Foundry project under **Management center** → **Connected resources**.
- **Instance Name** (`AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME`): The **configuration name** from your Bing Custom Search resource (Azure portal → your Bing Custom Search resource → **Configurations**). This is _not_ the Azure resource name or the connection name — it's the name of the specific search configuration that defines which domains/sites to search against.

## Run the sample

```powershell
dotnet run
```
