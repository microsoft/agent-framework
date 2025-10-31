# What This Sample Shows

This sample demonstrates how to use background responses with ChatCompletionAgent and Azure OpenAI Responses for long-running operations. Background responses support:

- **Polling for completion** - Non-streaming APIs can start a background operation and return a continuation token. Poll with the token until the response completes.
- **Function calling** - Functions can be called during background operations.
- **State persistence** - Thread and continuation token can be persisted and restored between polling cycles.

> **Note:** Background responses are currently only supported by OpenAI Responses.

For more information, see the [official documentation](https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-background-responses?pivots=programming-language-csharp).

# Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" # Replace with your Azure OpenAI resource endpoint
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5"  # Optional, defaults to gpt-5
```
