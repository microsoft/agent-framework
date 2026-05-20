# What this sample demonstrates

This sample demonstrates how to create an Azure AI Agent with the Deep Research Tool, which leverages the o3-deep-research reasoning model to perform comprehensive research on complex topics.

Key features:
- Configuring and using the Deep Research Tool with Bing grounding
- Creating a persistent AI agent with deep research capabilities
- Executing deep research queries and retrieving results

## Prerequisites

Before running this sample, ensure you have:

1. A Microsoft Foundry project set up
2. A deep research model deployment (e.g., o3-deep-research)
3. A model deployment (e.g., gpt-5.4-mini)
4. A Bing Connection configured in your Microsoft Foundry project
5. Azure CLI installed and authenticated

**Important**: Please visit the following documentation for detailed setup instructions:
- [Deep Research Tool Documentation](https://aka.ms/agents-deep-research)
- [Research Tool Setup](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/deep-research#research-tool-setup)

Pay special attention to the purple `Note` boxes in the Azure documentation.

**Note**: The Bing Grounding Connection ID must be the **full ARM resource URI** from the project, not just the connection name. It has the following format:

```
/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>/connections/<connection-name>
```

You can find this in the Microsoft Foundry portal under **Management > Connected resources**, or retrieve it programmatically via the connections API (`.id` property).

## Environment Variables

Set the following environment variables:

```powershell
# Replace with your Microsoft Foundry project endpoint
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/"

# Replace with your Bing Grounding connection ID (full ARM resource URI)
$env:AZURE_AI_BING_CONNECTION_ID="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>/connections/<connection-name>"

# Optional, defaults to o3-deep-research
$env:AZURE_AI_REASONING_DEPLOYMENT_NAME="o3-deep-research"

# Optional, defaults to gpt-5.4-mini
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
