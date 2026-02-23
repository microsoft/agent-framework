# Using Memory Search with AI Agents

This sample demonstrates how to use the Memory Search tool with AI agents. The Memory Search tool enables agents to recall information from previous conversations, supporting user profile persistence and chat summaries across sessions.

## What this sample demonstrates

- Creating an agent with Memory Search tool capabilities
- Configuring memory scope for user isolation
- Having conversations where the agent remembers past information
- Inspecting memory search results from agent responses
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- **A pre-created Memory Store** (see below)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

### Creating a Memory Store

Memory stores must be created before running this sample. The .NET SDK currently only supports **using** existing memory stores with agents. To create a memory store, use one of these methods:

**Option 1: Azure Portal**
1. Navigate to your Azure AI Foundry project
2. Go to the Memory section
3. Create a new memory store with your desired settings

**Option 2: Python SDK**
```python
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MemoryStoreDefaultDefinition, MemoryStoreDefaultOptions
from azure.identity import DefaultAzureCredential

project_client = AIProjectClient(
    endpoint="https://your-endpoint.openai.azure.com/",
    credential=DefaultAzureCredential()
)

memory_store = await project_client.memory_stores.create(
    name="my-memory-store",
    description="Memory store for Agent Framework conversations",
    definition=MemoryStoreDefaultDefinition(
        chat_model=os.environ["AZURE_AI_CHAT_MODEL_DEPLOYMENT_NAME"],
        embedding_model=os.environ["AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME"],
        options=MemoryStoreDefaultOptions(
            user_profile_enabled=True,
            chat_summary_enabled=True
        )
    )
)
```

## Environment Variables

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
$env:AZURE_AI_MEMORY_STORE_NAME="your-memory-store-name"  # Required - name of pre-created memory store
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/GettingStarted/FoundryAgents
dotnet run --project .\FoundryAgents_Step26_MemorySearch
```

## Expected behavior

The sample will:

1. Create an agent with Memory Search tool configured
2. Send a message with personal information ("My name is Alice and I love programming in C#")
3. Wait for memory indexing
4. Ask the agent to recall the previously shared information
5. Display memory search results if available in the response
6. Clean up by deleting the agent (note: memory store persists)

## Important notes

- **Memory Store Lifecycle**: Memory stores are long-lived resources and are NOT deleted when the agent is deleted. Clean them up separately via Azure Portal or Python SDK.
- **Scope**: The `scope` parameter isolates memories per user/context. Use unique identifiers for different users.
- **Update Delay**: The `UpdateDelay` parameter controls how quickly new memories are indexed.
