// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the Memory Search Tool with AI Agents.
// The Memory Search Tool enables agents to recall information from previous conversations,
// supporting user profile persistence and chat summaries across sessions.

using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using OpenAI.Responses;

string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string embeddingModelName = Environment.GetEnvironmentVariable("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME") ?? "text-embedding-ada-002";
string memoryStoreName = Environment.GetEnvironmentVariable("AZURE_AI_MEMORY_STORE_ID") ?? $"foundry-memory-sample-{Guid.NewGuid():N}";

const string AgentInstructions = """
    You are a helpful assistant that remembers past conversations.
    Use the memory search tool to recall relevant information from previous interactions.
    When a user shares personal details or preferences, remember them for future conversations.
    """;

const string AgentNameMEAI = "MemorySearchAgent-MEAI";
const string AgentNameNative = "MemorySearchAgent-NATIVE";

string userScope = $"user_{Environment.MachineName}";

MemorySearchPreviewTool memorySearchTool = new(memoryStoreName, userScope) { UpdateDelay = 0 };

// Create agent using Option 1 (MEAI) or Option 2 (Native SDK)
FoundryVersionedAgent agent = await CreateAgentWithMEAI();
// FoundryVersionedAgent agent = await CreateAgentWithNativeSDK();

AIProjectClient aiProjectClient = agent.GetService<AIProjectClient>()!;

// Ensure the memory store exists and has memories to retrieve.
await EnsureMemoryStoreAsync();

try
{
    Console.WriteLine("Agent created with Memory Search tool. Starting conversation...\n");

    // The agent uses the memory search tool to recall stored information.
    Console.WriteLine("User: What's my name and what programming language do I prefer?");
    AgentResponse response = await agent.RunAsync("What's my name and what programming language do I prefer?");
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
    // Cleanup: Delete the agent and memory store.
    Console.WriteLine("\nCleaning up...");
    await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
    Console.WriteLine("Agent deleted.");
    await aiProjectClient.MemoryStores.DeleteMemoryStoreAsync(memoryStoreName);
    Console.WriteLine("Memory store deleted.");
}

// Helpers — kept at the bottom so the main agent flow above stays clean.
async Task EnsureMemoryStoreAsync()
{
    Console.WriteLine($"Creating memory store '{memoryStoreName}'...");
    try
    {
        await aiProjectClient.MemoryStores.GetMemoryStoreAsync(memoryStoreName);
        Console.WriteLine("Memory store already exists.");
    }
    catch (System.ClientModel.ClientResultException ex) when (ex.Status == 404)
    {
        MemoryStoreDefaultDefinition definition = new(deploymentName, embeddingModelName);
        await aiProjectClient.MemoryStores.CreateMemoryStoreAsync(memoryStoreName, definition, "Sample memory store for Memory Search demo");
        Console.WriteLine("Memory store created.");
    }

    Console.WriteLine("Storing memories from a prior conversation...");
    MemoryUpdateOptions memoryOptions = new(userScope) { UpdateDelay = 0 };
    memoryOptions.Items.Add(ResponseItem.CreateUserMessageItem("My name is Alice and I love programming in C#."));

    MemoryUpdateResult updateResult = await aiProjectClient.MemoryStores.WaitForMemoriesUpdateAsync(
        memoryStoreName: memoryStoreName,
        pollingInterval: 500,
        options: memoryOptions);

    if (updateResult.Status == MemoryStoreUpdateStatus.Failed)
    {
        throw new InvalidOperationException($"Memory update failed: {updateResult.ErrorDetails}");
    }

    Console.WriteLine($"Memory update completed (status: {updateResult.Status}).\n");
}
#pragma warning disable CS8321 // Local function is declared but never used

// Option 1 - Using MemorySearchTool wrapped as MEAI AITool
async Task<FoundryVersionedAgent> CreateAgentWithMEAI()
{
    return await FoundryVersionedAgent.CreateAIAgentAsync(
        model: deploymentName,
        name: AgentNameMEAI,
        instructions: AgentInstructions,
        tools: [FoundryAITool.FromResponseTool(memorySearchTool)]);
}

// Option 2 - Using PromptAgentDefinition with MemorySearchTool (Native SDK)
async Task<FoundryVersionedAgent> CreateAgentWithNativeSDK()
{
    return await FoundryVersionedAgent.CreateAIAgentAsync(
        name: AgentNameNative,
        creationOptions: new AgentVersionCreationOptions(
            new PromptAgentDefinition(model: deploymentName)
            {
                Instructions = AgentInstructions,
                Tools = { memorySearchTool }
            })
    );
}
