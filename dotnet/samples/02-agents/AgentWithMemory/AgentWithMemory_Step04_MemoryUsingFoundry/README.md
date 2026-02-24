# Agent with Memory Using Azure AI Foundry

This sample demonstrates how to create and run an agent that uses Azure AI Foundry's managed memory service to extract and retrieve individual memories across sessions.

## Features Demonstrated

- Creating a `FoundryMemoryProvider` with Azure Identity authentication
- Automatic memory store creation if it doesn't exist
- Multi-turn conversations with automatic memory extraction
- Memory retrieval to inform agent responses
- Session serialization and deserialization
- Memory persistence across completely new sessions

## Prerequisites

1. Azure subscription with Azure AI Foundry project
2. Azure OpenAI resource with a chat model deployment (e.g., gpt-4o-mini) and an embedding model deployment (e.g., text-embedding-ada-002)
3. .NET 10.0 SDK
4. Azure CLI logged in (`az login`)

## Environment Variables

```bash
# Azure AI Foundry project endpoint and memory store name
export AZURE_AI_PROJECT_ENDPOINT="https://your-account.services.ai.azure.com/api/projects/your-project"
export AZURE_AI_MEMORY_STORE_ID="my_memory_store"

# Model deployment names (models deployed in your Foundry project)
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
export AZURE_AI_EMBEDDING_DEPLOYMENT_NAME="text-embedding-ada-002"
```

## Run the Sample

```bash
dotnet run
```

## Expected Output

The agent will:
1. Create the memory store if it doesn't exist (using the specified chat and embedding models)
2. Learn your name (Taylor), travel destination (Patagonia), timing (November), companions (sister), and interests (scenic viewpoints)
3. Wait for Foundry Memory to index the memories
4. Recall those details when asked about the trip
5. Demonstrate memory persistence across session serialization/deserialization
6. Show that a brand new session can still access the same memories

## Key Differences from Mem0

| Aspect | Mem0 | Azure AI Foundry Memory |
|--------|------|------------------------|
| Authentication | API Key | Azure Identity (DefaultAzureCredential) |
| Scope | ApplicationId, UserId, AgentId, ThreadId | Single `Scope` string |
| Memory Types | Single memory store | User Profile + Chat Summary |
| Hosting | Mem0 cloud or self-hosted | Azure AI Foundry managed service |
| Store Creation | N/A (automatic) | Explicit via `EnsureMemoryStoreCreatedAsync` |
