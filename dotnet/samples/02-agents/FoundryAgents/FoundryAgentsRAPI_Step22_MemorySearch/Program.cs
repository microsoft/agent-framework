// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the Memory Search Tool with a FoundryAgentClient.
// Memories are explicitly stored first via the MemoryStores API, then the MemorySearchPreviewTool
// is used by the agent to retrieve them during conversation.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string embeddingModelName = Environment.GetEnvironmentVariable("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME") ?? "text-embedding-ada-002";
string memoryStoreName = Environment.GetEnvironmentVariable("AZURE_AI_MEMORY_STORE_ID") ?? $"rapi-memory-sample-{Guid.NewGuid():N}";

const string AgentName = "MemorySearchAgent-RAPI";
string memoryScope = "travel-preferences";

DefaultAzureCredential credential = new();
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

// Ensure the memory store exists and has memories to retrieve.
await EnsureMemoryStoreAsync();

try
{
    // Create a FoundryResponsesAgent with the Memory Search tool.
    // The tool retrieves memories — it does NOT store new ones during conversation.
    MemorySearchPreviewTool memorySearchTool = new(memoryStoreName, memoryScope) { UpdateDelay = 0 };

    FoundryAgent agent = new(
        instructions: "You are a helpful travel assistant. Use the memory search tool to recall what you know about the user from past conversations.",
        name: AgentName,
        tools: [((ResponseTool)memorySearchTool).AsAITool()]);

    Console.WriteLine("Agent created. Asking about previously stored memories...\n");

    // The agent uses the memory search tool to recall stored information.
    Console.WriteLine("User: What do you remember about my upcoming trip?");
    AgentResponse response = await agent.RunAsync("What do you remember about my upcoming trip?");
    Console.WriteLine($"Agent: {response.Messages.LastOrDefault()?.Text}\n");

    // Inspect memory search results if available in raw response items.
    foreach (var message in response.Messages)
    {
        if (message.RawRepresentation is MemorySearchToolCallResponseItem memorySearchResult)
        {
            Console.WriteLine($"Memory Search Status: {memorySearchResult.Status}");
            Console.WriteLine($"Memory Search Results Count: {memorySearchResult.Results.Count}");

            foreach (var result in memorySearchResult.Results)
            {
                var memoryItem = result.MemoryItem;
                Console.WriteLine($"  - Memory ID: {memoryItem.MemoryId}");
                Console.WriteLine($"    Scope: {memoryItem.Scope}");
                Console.WriteLine($"    Content: {memoryItem.Content}");
                Console.WriteLine($"    Updated: {memoryItem.UpdatedAt}");
            }
        }
    }
}
finally
{
    // Cleanup: Delete the memory store.
    Console.WriteLine($"\nCleaning up memory store '{memoryStoreName}'...");
    await aiProjectClient.MemoryStores.DeleteMemoryStoreAsync(memoryStoreName);
    Console.WriteLine("Memory store deleted.");
}

// This creates a temporary memory to demonstrate the memory search functionality.
// In normal usage, the memories should be already present to be used by the tool.
async Task EnsureMemoryStoreAsync()
{
    // Create the store if it doesn't already exist.
    Console.WriteLine($"Creating memory store '{memoryStoreName}'...");
    try
    {
        await aiProjectClient.MemoryStores.GetMemoryStoreAsync(memoryStoreName);
        Console.WriteLine("Memory store already exists.");
    }
    catch (System.ClientModel.ClientResultException ex) when (ex.Status == 404)
    {
        MemoryStoreDefaultDefinition definition = new(deploymentName, embeddingModelName);
        await aiProjectClient.MemoryStores.CreateMemoryStoreAsync(memoryStoreName, definition, "Sample memory store for RAPI Memory Search demo");
        Console.WriteLine("Memory store created.");
    }

    // Explicitly add memories from a simulated prior conversation.
    Console.WriteLine("Storing memories from a prior conversation...");
    MemoryUpdateOptions memoryOptions = new(memoryScope) { UpdateDelay = 0 };
    memoryOptions.Items.Add(ResponseItem.CreateUserMessageItem("My name is Alice and I'm planning a trip to Japan next spring."));

    MemoryUpdateResult updateResult = await aiProjectClient.MemoryStores.WaitForMemoriesUpdateAsync(
        memoryStoreName: memoryStoreName,
        options: memoryOptions,
        pollingInterval: 500);

    if (updateResult.Status == MemoryStoreUpdateStatus.Failed)
    {
        throw new InvalidOperationException($"Memory update failed: {updateResult.ErrorDetails}");
    }

    Console.WriteLine($"Memory update completed (status: {updateResult.Status}).");

    // Quick verification that memories are searchable.
    Console.WriteLine("Verifying stored memories...");
    MemorySearchOptions searchOptions = new(memoryScope)
    {
        Items = { ResponseItem.CreateUserMessageItem("What are Alice's travel preferences?") }
    };
    MemoryStoreSearchResponse searchResult = await aiProjectClient.MemoryStores.SearchMemoriesAsync(
        memoryStoreName: memoryStoreName,
        options: searchOptions);

    foreach (var memory in searchResult.Memories)
    {
        Console.WriteLine($"  - {memory.MemoryItem.Content}");
    }

    Console.WriteLine();
}
