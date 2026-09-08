# Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
# Resource root is fine (sample appends /openai/v1). You can also set the full v1 endpoint.
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
# or: $env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/openai/v1/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"  # Optional, defaults to gpt-5.4-mini
```
