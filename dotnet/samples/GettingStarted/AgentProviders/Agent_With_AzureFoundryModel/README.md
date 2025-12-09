## Overview

This sample shows how to use the OpenAI SDK to create and use a simple AI agent with any model hosted in Azure AI Foundry.

You could use models from Microsoft, OpenAI, DeepSeek, Hugging Face, Meta, xAI or any other model you have deployed in Azure AI Foundry.

**Note**: Ensure that you pick a model that suits your needs. For example, if you want to use function calling, ensure that the model you pick supports function calling.

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure AI Foundry resource
- A model deployment in your Azure AI Foundry resource. This example defaults to using the `Phi-4-mini-instruct` model,
so if you want to use a different model, ensure that you set your `AZURE_FOUNDRY_MODEL_DEPLOYMENT` environment
variable to the name of your deployed model.
- An API key or role based authentication to access the Azure AI Foundry resource

See [here](https://learn.microsoft.com/en-us/azure/ai-foundry/quickstarts/get-started-code?tabs=csharp) for more info on setting up these prerequisites

Set the following environment variables:

```powershell
# Replace with your Azure AI Foundry resource endpoint
# Ensure that you have the "/openai/v1/" path in the URL, since this is required when using the OpenAI SDK to access Azure Foundry models.
$env:AZURE_FOUNDRY_OPENAI_ENDPOINT="https://ai-foundry-<myresourcename>.services.ai.azure.com/openai/v1/"

# Optional, defaults to using Azure CLI for authentication if not provided
$env:AZURE_FOUNDRY_OPENAI_APIKEY="************"

# Optional, defaults to Phi-4-mini-instruct
$env:AZURE_FOUNDRY_MODEL_DEPLOYMENT="Phi-4-mini-instruct"
```
