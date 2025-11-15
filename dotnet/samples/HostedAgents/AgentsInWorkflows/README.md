# What this sample demonstrates

This sample demonstrates the use of AI agents as executors within a workflow.

This workflow uses three translation agents:
1. French Agent - translates input text to French
2. Spanish Agent - translates French text to Spanish
3. English Agent - translates Spanish text back to English

The agents are connected sequentially, creating a translation chain that demonstrates how AI-powered components can be seamlessly integrated into workflow pipelines.

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" # Replace with your Azure OpenAI resource endpoint
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini