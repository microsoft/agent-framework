# What this sample demonstrates

This sample demonstrates how to create an Azure AI Agent with the Deep Research Tool, which leverages the o3-deep-research reasoning model to perform comprehensive research on complex topics.

Key features:
- Configuring and using the Deep Research Tool with Bing grounding
- Creating a persistent AI agent with deep research capabilities
- Executing deep research queries and retrieving results

## Prerequisites

Before running this sample, ensure you have:

1. An Azure AI Foundry project set up
2. A deep research model deployment (e.g., o3-deep-research)
3. A model deployment (e.g., gpt-4o)
4. A Bing Connection configured in your Azure AI Foundry project
5. Azure CLI installed and authenticated

**Important**: Please visit the following documentation for detailed setup instructions:
- [Deep Research Tool Documentation](https://aka.ms/agents-deep-research)
- [Research Tool Setup](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/deep-research#research-tool-setup)

Pay special attention to the purple `Note` boxes in the Azure documentation.

**Note**: The Bing Connection ID must be from the **project**, not the resource. It has the following format:

```
/subscriptions/<sub_id>/resourceGroups/<rg_name>/providers/<provider_name>/accounts/<account_name>/projects/<project_name>/connections/<connection_name>
```

## Environment Variables

Set the following environment variables:

```powershell
# Replace with your Azure AI Foundry project endpoint
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/"

# Replace with your Bing connection ID from the project
$env:BING_CONNECTION_ID="/subscriptions/.../connections/your-bing-connection"

# Optional, defaults to o3-deep-research
$env:AZURE_FOUNDRY_PROJECT_DEEP_RESEARCH_DEPLOYMENT_NAME="o3-deep-research"

# Optional, defaults to gpt-4o
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o"
