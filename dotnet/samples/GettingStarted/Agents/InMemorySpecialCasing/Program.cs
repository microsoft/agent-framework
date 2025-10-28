// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to persist and reload an agent thread and chat history separately
// using the in-memory message store. It shows how to:
// 1. Try to load a serialized thread and chat history in parallel.
// 2. Create a new thread and empty chat history if none exist.
// 3. Merge any loaded chat history into the thread's current store.
// 4. Run the agent with the reconstructed state.
// 5. Extract, clear, and persist the updated chat history and thread state for later use.

using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;

// Main sample logic -----------------------------------------------------------------------------

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Construct the agent with default in-memory chat message store behavior.
// In this case the special casing will be applied.
AIAgent chatCompletionAgent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

DeleteChatHistory("sampleId");
DeleteThread("sampleId");
await RunAgent(chatCompletionAgent, "sampleId", "Tell me a joke about a pirate.");
await RunAgent(chatCompletionAgent, "sampleId", "Now add some emojis to the same joke.");

// Now construct a responses based agent that stores chat history in the service and not in-memory.
// In this case the special casing will be skipped.
AIAgent responsesAgent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetOpenAIResponseClient(deploymentName)
    .CreateAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

DeleteChatHistory("sampleId");
DeleteThread("sampleId");
await RunAgent(responsesAgent, "sampleId", "Tell me a joke about a pirate.");
await RunAgent(responsesAgent, "sampleId", "Now add some emojis to the same joke.");

static async Task RunAgent(AIAgent agent, string conversationId, string userMessage)
{
    // Attempt to load thread and chat history simultaneously.
    Task<AgentThread?> loadThreadTask = TryLoadThreadAsync(conversationId, agent);
    Task<IList<ChatMessage>?> loadChatHistoryTask = TryLoadChatHistoryAsync(conversationId);

    AgentThread? loadedThread = await loadThreadTask;
    IList<ChatMessage>? loadedChatHistory = await loadChatHistoryTask;

    // If no thread exists, create a new one.
    AgentThread thread = loadedThread ?? agent.GetNewThread();

    // Get the in-memory chat history store registered on the thread.
    InMemoryChatMessageStore? threadChatHistory = thread.GetService<InMemoryChatMessageStore>();

    // If we loaded chat history, and we are dealing with in memory chat history, set it on the thread's store.
    if (threadChatHistory is not null && loadedChatHistory is { Count: > 0 })
    {
        threadChatHistory.Clear();
        foreach (ChatMessage m in loadedChatHistory)
        {
            threadChatHistory.Add(m);
        }
    }

    // Run the agent with the thread.
    Console.WriteLine(await agent.RunAsync(userMessage, thread));

    // After running, capture the updated chat history.
    InMemoryChatMessageStore? updatedChatHistory = thread.GetService<InMemoryChatMessageStore>();

    // If we are dealing with in-memory chat history, extract and persist it separately.
    if (updatedChatHistory is not null)
    {
        // Create a copy we will persist.
        List<ChatMessage> toPersist = new(updatedChatHistory);

        // Clear messages in the thread's list (special casing scenario where thread should store minimal state).
        updatedChatHistory.Clear();

        // Persist thread and chat history separately.
        Task persistThreadtask = PersistThreadAsync(conversationId, thread);
        Task persistChatHistoryTask = PersistChatHistoryAsync(conversationId, toPersist);
        await persistThreadtask;
        await persistChatHistoryTask;
    }
    // Otherwise, just persist the thread as usual.
    else
    {
        await PersistThreadAsync(conversationId, thread);
    }
}

// Helper methods for thread persistence ---------------------------------------------------------

static async Task PersistThreadAsync(string id, AgentThread thread)
{
    JsonElement serialized = thread.Serialize();
    string path = GetThreadPath(id);
    Directory.CreateDirectory(Path.GetDirectoryName(path)!);
    await File.WriteAllTextAsync(path, JsonSerializer.Serialize(serialized));
}

static async Task<AgentThread?> TryLoadThreadAsync(string id, AIAgent agent)
{
    string path = GetThreadPath(id);
    if (!File.Exists(path))
    {
        return null;
    }

    try
    {
        JsonElement element = JsonSerializer.Deserialize<JsonElement>(await File.ReadAllTextAsync(path));
        return agent.DeserializeThread(element);
    }
    catch
    {
        return null; // Corrupt or incompatible, ignore for sample simplicity
    }
}

static void DeleteThread(string id)
{
    string path = GetThreadPath(id);
    if (File.Exists(path))
    {
        File.Delete(path);
    }
}

static string GetThreadPath(string id) => Path.Combine(Path.GetTempPath(), "inmemory-specialcasing", $"thread_{id}.json");

// Helper methods for chat history persistence ---------------------------------------------------

static async Task PersistChatHistoryAsync(string id, IList<ChatMessage> chatHistory)
{
    // Serialize only the messages
    string path = GetChatHistoryPath(id);
    Directory.CreateDirectory(Path.GetDirectoryName(path)!);
    await File.WriteAllTextAsync(path, JsonSerializer.Serialize(chatHistory));
}

static async Task<IList<ChatMessage>?> TryLoadChatHistoryAsync(string id)
{
    string path = GetChatHistoryPath(id);
    if (!File.Exists(path))
    {
        return null;
    }

    try
    {
        var messages = JsonSerializer.Deserialize<List<ChatMessage>>(await File.ReadAllTextAsync(path));
        return messages ?? new List<ChatMessage>();
    }
    catch
    {
        return null;
    }
}

static void DeleteChatHistory(string id)
{
    string path = GetChatHistoryPath(id);
    if (File.Exists(path))
    {
        File.Delete(path);
    }
}

static string GetChatHistoryPath(string id) => Path.Combine(Path.GetTempPath(), "inmemory-specialcasing", $"chat_{id}.json");
