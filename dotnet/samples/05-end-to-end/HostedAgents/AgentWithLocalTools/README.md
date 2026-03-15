# What this sample demonstrates

This sample demonstrates how to build a hosted agent that uses local C# function tools — a key advantage of code-based hosted agents over prompt agents. The agent acts as a Seattle travel assistant with a `GetAvailableHotels` tool that simulates querying a hotel availability API.

Key features:
- Defining local C# functions as agent tools using `AIFunctionFactory`
- Using `AIProjectClient` to discover the OpenAI connection from the Azure AI Foundry project
- Building a `ChatClientAgent` with custom instructions and tools
- Deploying to the Foundry Hosted Agent service

> For common prerequisites and setup instructions, see the [Hosted Agent Samples README](../README.md).

## Prerequisites

Before running this sample, ensure you have:

1. .NET 10 SDK installed
2. An Azure AI Foundry Project with a chat model deployed (e.g., gpt-4o-mini)
3. Azure CLI installed and authenticated (`az login`)

## Environment Variables

Set the following environment variables:

```powershell
# Replace with your Azure AI Foundry project endpoint
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project-name"

# Optional, defaults to gpt-4o-mini
$env:MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

## How It Works

1. The agent uses `AIProjectClient` to discover the Azure OpenAI connection from the project endpoint
2. A local C# function `GetAvailableHotels` is registered as a tool using `AIFunctionFactory.Create`
3. When users ask about hotels, the model invokes the local tool to search simulated hotel data
4. The tool filters hotels by price and calculates total costs based on the requested dates
5. Results are returned to the model, which presents them in a conversational format
