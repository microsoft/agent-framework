// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the Memory Search Tool with AI Agents.
// The Memory Search Tool enables agents to recall information from previous conversations,
// supporting user profile persistence and chat summaries across sessions.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Memory store configuration
// NOTE: Memory stores must be created beforehand via Azure Portal or Python SDK.
// The .NET SDK currently only supports using existing memory stores with agents.
string memoryStoreName = Environment.GetEnvironmentVariable("AZURE_AI_MEMORY_STORE_ID") ?? throw new InvalidOperationException("AZURE_AI_MEMORY_STORE_ID is not set.");

const string AgentInstructions = """
    You are a helpful assistant that remembers past conversations.
    Use the memory search tool to recall relevant information from previous interactions.
    When a user shares personal details or preferences, remember them for future conversations.
    """;

const string AgentNameMEAI = "MemorySearchAgent-MEAI";
const string AgentNameNative = "MemorySearchAgent-NATIVE";

// Scope identifies the user or context for memory isolation.
// Using a unique user identifier ensures memories are private to that user.
string userScope = $"user_{Environment.MachineName}";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// Create the Memory Search tool configuration
MemorySearchTool memorySearchTool = new(memoryStoreName, userScope)
{
    // Optional: Configure how quickly new memories are indexed (in seconds)
    UpdateDelay = 1,

    // Optional: Configure search behavior
    SearchOptions = new MemorySearchToolOptions
    {
        // Additional search options can be configured here if needed
    }
};

// Create agent using Option 1 (MEAI) or Option 2 (Native SDK)
AIAgent agent = await CreateAgentWithMEAI();
// AIAgent agent = await CreateAgentWithNativeSDK();

Console.WriteLine("Agent created with Memory Search tool. Starting conversation...\n");

// Conversation 1: Share some personal information
Console.WriteLine("User: My name is Alice and I love programming in C#.");
AgentResponse response1 = await agent.RunAsync("My name is Alice and I love programming in C#.");
Console.WriteLine($"Agent: {response1.Messages.LastOrDefault()?.Text}\n");

// Allow time for memory to be indexed
await Task.Delay(2000);

// Conversation 2: Test if the agent remembers
Console.WriteLine("User: What's my name and what programming language do I prefer?");
AgentResponse response2 = await agent.RunAsync("What's my name and what programming language do I prefer?");
Console.WriteLine($"Agent: {response2.Messages.LastOrDefault()?.Text}\n");

// Inspect memory search results if available in raw response items
// Note: Memory search tool call results appear as AgentResponseItem types
foreach (var message in response2.Messages)
{
    if (message.RawRepresentation is AgentResponseItem agentResponseItem &&
        agentResponseItem is MemorySearchToolCallResponseItem memorySearchResult)
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

// Cleanup: Delete the agent (memory store persists and should be cleaned up separately if needed)
Console.WriteLine("\nCleaning up agent...");
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
Console.WriteLine("Agent deleted successfully.");

// NOTE: Memory stores are long-lived resources and are NOT deleted with the agent.
// To delete a memory store, use the Azure Portal or Python SDK:
// await project_client.memory_stores.delete(memory_store.name)

// --- Agent Creation Options ---
#pragma warning disable CS8321 // Local function is declared but never used

// Option 1 - Using MemorySearchTool wrapped as MEAI AITool
async Task<AIAgent> CreateAgentWithMEAI()
{
    return await aiProjectClient.CreateAIAgentAsync(
        model: deploymentName,
        name: AgentNameMEAI,
        instructions: AgentInstructions,
        tools: [((ResponseTool)memorySearchTool).AsAITool()]);
}

// Option 2 - Using PromptAgentDefinition with MemorySearchTool (Native SDK)
async Task<AIAgent> CreateAgentWithNativeSDK()
{
    return await aiProjectClient.CreateAIAgentAsync(
        name: AgentNameNative,
        creationOptions: new AgentVersionCreationOptions(
            new PromptAgentDefinition(model: deploymentName)
            {
                Instructions = AgentInstructions,
                Tools = { memorySearchTool }
            })
    );
}
