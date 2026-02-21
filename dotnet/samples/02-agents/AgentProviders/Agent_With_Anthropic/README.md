# Creating an AIAgent with Anthropic

This sample demonstrates how to create an AIAgent using Anthropic Claude models as the underlying inference service.

The sample supports three deployment scenarios:

1. **Anthropic Public API** - Direct connection to Anthropic's public API
2. **Azure Foundry with API Key** - Anthropic models deployed through Azure Foundry using API key authentication
3. **Azure Foundry with Azure CLI** - Anthropic models deployed through Azure Foundry using Azure CLI credentials

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later

### For Anthropic Public API

- Anthropic API key

Set the following environment variables:

```powershell
$env:ANTHROPIC_API_KEY="your-anthropic-api-key"  # Replace with your Anthropic API key
$env:ANTHROPIC_DEPLOYMENT_NAME="claude-haiku-4-5"  # Optional, defaults to claude-haiku-4-5
```

### For Azure Foundry with API Key

- Azure Foundry service endpoint and deployment configured
- Anthropic API key

Set the following environment variables:

```powershell
$env:ANTHROPIC_RESOURCE="your-foundry-resource-name"  # Replace with your Azure Foundry resource name (subdomain before .services.ai.azure.com)
$env:ANTHROPIC_API_KEY="your-anthropic-api-key"  # Replace with your Anthropic API key
$env:ANTHROPIC_DEPLOYMENT_NAME="claude-haiku-4-5"  # Optional, defaults to claude-haiku-4-5
```

### For Azure Foundry with Azure CLI

- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

Set the following environment variables:

```powershell
$env:ANTHROPIC_RESOURCE="your-foundry-resource-name"  # Replace with your Azure Foundry resource name (subdomain before .services.ai.azure.com)
$env:ANTHROPIC_DEPLOYMENT_NAME="claude-haiku-4-5"  # Optional, defaults to claude-haiku-4-5
```

**Note**: When using Azure Foundry with Azure CLI, make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).
