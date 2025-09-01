# Microsoft Agent Framework Getting Started

This guide will help you get up and running quickly with a basic agent using the Agent Framework and Azure OpenAI.

## Prerequisites

Before you begin, ensure you have the following:

- [.NET 8.0 SDK or later](https://dotnet.microsoft.com/download)
- An [Azure OpenAI](https://learn.microsoft.com/azure/ai-services/openai/) resource with a deployed model (e.g., `gpt-4o-mini`)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed and authenticated (`az login`)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Running a Basic Agent Sample

This sample demonstrates how to create and use a simple AI agent with Azure OpenAI as the backend. It will create a basic agent using `AzureOpenAIClient` with `gpt-4o-mini` and custom instructions.

Make sure to replace `https://your-resource.openai.azure.com/` with the endpoint of your Azure OpenAI resource.

### Sample Code

```csharp
using System;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;
using OpenAI;

AIAgent agent = new AzureOpenAIClient(
  new Uri("https://your-resource.openai.azure.com/"),
  new AzureCliCredential())
    .GetChatClient("gpt-4o-mini")
    .CreateAIAgent(instructions: "You are good at telling jokes.");

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
```

For more details and more advanced scenarios, see [Getting Started Steps](../../../dotnet/samples/GettingStartedSteps/).


