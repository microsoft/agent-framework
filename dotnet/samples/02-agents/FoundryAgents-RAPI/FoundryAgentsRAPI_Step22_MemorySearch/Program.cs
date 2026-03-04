// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the Memory Search Tool with a FoundryAgentClient using the Responses API directly.
// The Memory Search Tool enables agents to recall information from previous conversations.

using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Memory store configuration
// NOTE: Memory stores must be created beforehand via Azure Portal or Python SDK.
string memoryStoreName = Environment.GetEnvironmentVariable("AZURE_AI_MEMORY_STORE_ID") ?? throw new InvalidOperationException("AZURE_AI_MEMORY_STORE_ID is not set.");

const string AgentInstructions = """
    You are a helpful assistant that remembers past conversations.
    Use the memory search tool to recall relevant information from previous interactions.
    When a user shares personal details or preferences, remember them for future conversations.
    """;

const string AgentName = "MemorySearchAgent-RAPI";

// Scope identifies the user or context for memory isolation.
string userScope = $"user_{Environment.MachineName}";

// Create the Memory Search tool configuration
MemorySearchPreviewTool memorySearchTool = new(memoryStoreName, userScope)
{
    UpdateDelay = 1,
    SearchOptions = new MemorySearchToolOptions()
};

// Create a FoundryAgentClient with Memory Search tool using the Responses API directly.
// No server-side agent is created.
FoundryAgentClient agent = new(
    endpoint: new Uri(endpoint),
    tokenProvider: new AzureCliCredential(),
    model: deploymentName,
    instructions: AgentInstructions,
    name: AgentName,
    tools: [((ResponseTool)memorySearchTool).AsAITool()]);

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
