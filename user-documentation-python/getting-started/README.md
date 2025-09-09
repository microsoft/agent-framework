# Microsoft Agent Framework Getting Started

This guide will help you get up and running quickly with a basic agent using the Agent Framework and Azure AI Foundry.

## Prerequisites

Before you begin, ensure you have the following:

- [Python 3.9 or later](https://www.python.org/downloads/)
- An [Azure AI Foundry](https://learn.microsoft.com/azure/ai-foundry/) project with a deployed model (e.g., `gpt-4o-mini`)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed and authenticated (`az login`)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure AI Foundry project. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Running a Basic Agent Sample

This sample demonstrates how to create and use a simple AI agent with Azure AI Foundry as the backend. It will create a basic agent using `ChatAgent` with `FoundryChatClient` and custom instructions.

Make sure to set the following environment variables:
- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL_DEPLOYMENT_NAME`: The name of your model deployment

For detailed information about different ways to run examples and configure environment variables, see [Running Examples Guide](running_examples.md).

### Sample Code

```python
import asyncio
from agent_framework import ChatAgent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async def main():
    async with (
        AzureCliCredential() as credential,
        ChatAgent(
            chat_client=FoundryChatClient(async_credential=credential),
            instructions="You are good at telling jokes."
        ) as agent,
    ):
        result = await agent.run("Tell me a joke about a pirate.")
        print(result.text)

if __name__ == "__main__":
    asyncio.run(main())
```

## More Examples

For more detailed examples and advanced scenarios, see the [Foundry Agent Examples](../../python/samples/getting_started/agents/foundry/README.md).
