# What This Sample Shows

This sample demonstrates how to use background responses with ChatCompletionAgent and Azure OpenAI Responses for long-running operations. Background responses support:

- **Polling for completion** - Non-streaming APIs can start a background operation and return a continuation token. Poll with the token until the response completes.
- **Resuming after interruption** - Streaming APIs can be interrupted and resumed from the last update using the continuation token.

> **Note:** Background responses are currently only supported by OpenAI Responses.

For more information, see the [official documentation](https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-background-responses?pivots=programming-language-csharp).

# Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Microsoft Foundry project endpoint and model configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Foundry project. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Foundry project endpoint
$env:FOUNDRY_MODEL="gpt-5.4-mini"  # Optional, defaults to gpt-5.4-mini
```