# Agent with Memory Using Azure AI Foundry

This sample demonstrates how to create and run an agent that uses Azure AI Foundry's managed memory service to extract and retrieve individual memories across sessions.

## Features Demonstrated

- Creating a `FoundryMemoryProvider` with Azure Identity authentication
- Multi-turn conversations with automatic memory extraction
- Memory retrieval to inform agent responses
- Session serialization and deserialization
- Memory persistence across completely new sessions

## Prerequisites

1. Azure subscription with Azure AI Foundry project
2. Memory store created in your Foundry project (see setup below)
3. Azure OpenAI resource with a chat model deployment (e.g., gpt-4o-mini)
4. .NET 10.0 SDK
5. Azure CLI logged in (`az login`)

## Setup Memory Store

1. Navigate to your [Azure AI Foundry project](https://ai.azure.com/)
2. Go to **Agents** > **Memory stores**
3. Create a new memory store with:
   - A chat model deployment for memory extraction
   - An embedding model deployment for semantic search
   - Enable user profile memory and/or chat summary memory

## Environment Variables

```bash
# Azure AI Foundry project endpoint and memory store name
export AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-account.services.ai.azure.com/api/projects/your-project"
export FOUNDRY_MEMORY_STORE_NAME="my_memory_store"

# Azure OpenAI deployment name (model deployed in your Foundry project)
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
```

## Run the Sample

```bash
dotnet run
```

## Expected Output

The agent will:
1. Learn your name (Taylor), travel destination (Patagonia), timing (November), companions (sister), and interests (scenic viewpoints)
2. Wait for Foundry Memory to index the memories
3. Recall those details when asked about the trip
4. Demonstrate memory persistence across session serialization/deserialization
5. Show that a brand new session can still access the same memories

## Key Differences from Mem0

| Aspect | Mem0 | Azure AI Foundry Memory |
|--------|------|------------------------|
| Authentication | API Key | Azure Identity (DefaultAzureCredential) |
| Scope | ApplicationId, UserId, AgentId, ThreadId | Single `Scope` string |
| Memory Types | Single memory store | User Profile + Chat Summary |
| Hosting | Mem0 cloud or self-hosted | Azure AI Foundry managed service |
