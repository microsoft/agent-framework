// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CA1869 // Cache and reuse 'JsonSerializerOptions' instances

// This sample shows how to create and use a simple AI agent with a conversation that can be persisted to disk.

using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.VectorData;
using Microsoft.SemanticKernel.Connectors.InMemory;
using OpenAI.Chat;
using SampleApp;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create a vector store to store the chat messages in.
// Replace this with a vector store implementation of your choice if you want to persist the chat history to disk.
VectorStore vectorStore = new InMemoryVectorStore();

// Execute various samples showing how to use a custom ChatMessageStore with an agent.
await CustomChatMessageStore_UsingFactory_Async();
await CustomChatMessageStore_UsingFactoryAndExistingExternalId_Async();
await CustomChatMessageStore_PerThread_Async();
await CustomChatMessageStore_PerRun_Async();

// Here we can see how to create a custom ChatMessageStore using a factory method
// provided to the agent via the ChatMessageStoreFactory option.
// This allows us to use a custom chat message store, where the consumer of the agent
// doesn't need to know anything about the storage mechanism used.
async Task CustomChatMessageStore_UsingFactory_Async()
{
    Console.WriteLine("\n--- With Factory ---\n");

    // Create the agent
    AIAgent agent = new AzureOpenAIClient(
        new Uri(endpoint),
        new AzureCliCredential())
        // Use a service that doesn't require storage of chat history in the service itself.
        .GetChatClient(deploymentName)
        .CreateAIAgent(new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "You are good at telling jokes." },
            Name = "Joker",
            ChatMessageStoreFactory = ctx =>
            {
                // Create a new chat message store for this agent that stores the messages in a vector store.
                // Each thread must get its own copy of the VectorChatMessageStore, since the store
                // also contains the id that the thread is stored under.
                return new VectorChatMessageStore(vectorStore, ctx.SerializedState, ctx.JsonSerializerOptions, ctx.Features);
            }
        });

    // Start a new thread for the agent conversation.
    AgentThread thread = agent.GetNewThread();

    // Run the agent with the thread that stores conversation history in the vector store.
    Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));

    // Serialize the thread state, so it can be stored for later use.
    // Since the chat history is stored in the vector store, the serialized thread
    // only contains the guid that the messages are stored under in the vector store.
    JsonElement serializedThread = thread.Serialize();

    Console.WriteLine("\n--- Serialized thread ---\n");
    Console.WriteLine(JsonSerializer.Serialize(serializedThread, new JsonSerializerOptions { WriteIndented = true }));

    // The serialized thread can now be saved to a database, file, or any other storage mechanism
    // and loaded again later.

    // Deserialize the thread state after loading from storage.
    AgentThread resumedThread = agent.DeserializeThread(serializedThread);

    // Run the agent with the thread that stores conversation history in the vector store a second time.
    Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate, and add some emojis to the joke.", resumedThread));
}

// Here we can see how to create a custom ChatMessageStore using a factory method
// provided to the agent via the ChatMessageStoreFactory option.
// It also shows how we can pass a custom storage id at runtime to the message store using
// the VectorChatMessageStoreThreadDbKeyFeature.
// Note that not all agents or chat message stores may support this feature.
async Task CustomChatMessageStore_UsingFactoryAndExistingExternalId_Async()
{
    Console.WriteLine("\n--- With Factory and Existing External ID ---\n");

    // Create the agent
    AIAgent agent = new AzureOpenAIClient(
        new Uri(endpoint),
        new AzureCliCredential())
        // Use a service that doesn't require storage of chat history in the service itself.
        .GetChatClient(deploymentName)
        .CreateAIAgent(new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "You are good at telling jokes." },
            Name = "Joker",
            ChatMessageStoreFactory = ctx =>
            {
                // Create a new chat message store for this agent that stores the messages in a vector store.
                // Each thread must get its own copy of the VectorChatMessageStore, since the store
                // also contains the id that the thread is stored under.
                return new VectorChatMessageStore(vectorStore, ctx.SerializedState, ctx.JsonSerializerOptions, ctx.Features);
            }
        });

    // Start a new thread for the agent conversation.
    AgentThread thread = agent.GetNewThread();

    // Run the agent with the thread that stores conversation history in the vector store.
    Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));

    // We can access the VectorChatMessageStore via the thread's GetService method if we need to read the key under which threads are stored.
    var messageStoreFromFactory = thread.GetService<VectorChatMessageStore>()!;
    Console.WriteLine($"\nThread is stored in vector store under key: {messageStoreFromFactory.ThreadDbKey}");

    // It's possible to create a new thread that uses the same chat message store id by providing
    // the VectorChatMessageStoreThreadDbKeyFeature in the feature collection when creating the new thread.
    AgentThread resumedThread = agent.GetNewThread(
        new AgentFeatureCollection().WithFeature(new VectorChatMessageStoreThreadDbKeyFeature(messageStoreFromFactory.ThreadDbKey!)));

    // Run the agent with the thread that stores conversation history in the vector store.
    Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate, and add some emojis to the joke.", resumedThread));
}

// Here we can see how to create a custom ChatMessageStore and pass it to the thread
// when creating a new thread.
async Task CustomChatMessageStore_PerThread_Async()
{
    Console.WriteLine("\n--- Per Thread ---\n");

    // We can also create an agent without a factory that provides a ChatMessageStore.
    AIAgent agent = new AzureOpenAIClient(
        new Uri(endpoint),
        new AzureCliCredential())
        // Use a service that doesn't require storage of chat history in the service itself.
        .GetChatClient(deploymentName)
        .CreateAIAgent(new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "You are good at telling jokes." },
            Name = "Joker"
        });

    // Instead of using a factory on the agent to create the ChatMessageStore, we can
    // create a VectorChatMessageStore ourselves and register it in a feature collection.
    // We can then pass the feature collection when creating a new thread.
    // We also have the opportunity here to pass any id that we want for storing the chat history in the vector store.
    VectorChatMessageStore perThreadMessageStore = new(vectorStore, "chat-history-1");
    AgentThread thread = agent.GetNewThread(new AgentFeatureCollection().WithFeature<ChatMessageStore>(perThreadMessageStore));

    Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));

    // When serializing this thread, we'll see that it has the id from the message store stored in its state.
    JsonElement serializedThread = thread.Serialize();

    Console.WriteLine("\n--- Serialized thread ---\n");
    Console.WriteLine(JsonSerializer.Serialize(serializedThread, new JsonSerializerOptions { WriteIndented = true }));
}

// Here we can see how to create a custom ChatMessageStore for a single run using the Features option
// passed when we run the agent.
// Note that if the agent doesn't support a chat message store, it would be ignored.
async Task CustomChatMessageStore_PerRun_Async()
{
    Console.WriteLine("\n--- Per Run ---\n");

    // We can also create an agent without a factory that provides a ChatMessageStore.
    AIAgent agent = new AzureOpenAIClient(
        new Uri(endpoint),
        new AzureCliCredential())
        // Use a service that doesn't require storage of chat history in the service itself.
        .GetChatClient(deploymentName)
        .CreateAIAgent(new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "You are good at telling jokes." },
            Name = "Joker"
        });

    // Start a new thread for the agent conversation.
    AgentThread thread = agent.GetNewThread();

    // Instead of using a factory on the agent to create the ChatMessageStore, we can
    // create a VectorChatMessageStore ourselves and register it in a feature collection.
    // We can then pass the feature collection to the agent when running it by using the Features option.
    // The message store would only be used for the run that it's passed to.
    // If the agent doesn't support a message store, it would be ignored.
    // We also have the opportunity here to pass any id that we want for storing the chat history in the vector store.
    VectorChatMessageStore perRunMessageStore = new(vectorStore, "chat-history-1");
    Console.WriteLine(await agent.RunAsync(
        "Tell me a joke about a pirate.",
        thread,
        options: new AgentRunOptions()
        {
            Features = new AgentFeatureCollection().WithFeature<ChatMessageStore>(perRunMessageStore)
        }));

    // When serializing this thread, we'll see that it has no messagestore state, since the messagestore was not attached to the thread,
    // but just provided for the single run. Note that, depending on the circumstances, the thread may still contain other state, e.g. Memories,
    // if an AIContextProvider is attached which adds memory to an agent.
    JsonElement serializedThread = thread.Serialize();

    Console.WriteLine("\n--- Serialized thread ---\n");
    Console.WriteLine(JsonSerializer.Serialize(serializedThread, new JsonSerializerOptions { WriteIndented = true }));
}

namespace SampleApp
{
    /// <summary>
    /// A feature that allows providing the thread database key for the <see cref="VectorChatMessageStore"/>.
    /// </summary>
    internal sealed class VectorChatMessageStoreThreadDbKeyFeature(string threadDbKey)
    {
        public string ThreadDbKey { get; } = threadDbKey;
    }

    /// <summary>
    /// A sample implementation of <see cref="ChatMessageStore"/> that stores chat messages in a vector store.
    /// </summary>
    internal sealed class VectorChatMessageStore : ChatMessageStore
    {
        private readonly VectorStore _vectorStore;

        public VectorChatMessageStore(VectorStore vectorStore, string threadDbKey)
        {
            this._vectorStore = vectorStore ?? throw new ArgumentNullException(nameof(vectorStore));
            this.ThreadDbKey = threadDbKey ?? throw new ArgumentNullException(nameof(threadDbKey));
        }

        public VectorChatMessageStore(VectorStore vectorStore, JsonElement serializedStoreState, JsonSerializerOptions? jsonSerializerOptions = null, IAgentFeatureCollection? features = null)
        {
            this._vectorStore = vectorStore ?? throw new ArgumentNullException(nameof(vectorStore));

            // Here we can deserialize the thread id so that we can access the same messages as before the suspension, or if
            // a user provided a ConversationIdAgentFeature in the features collection, we can use that
            // or finally we can generate one ourselves.
            this.ThreadDbKey = serializedStoreState.ValueKind is JsonValueKind.String
                ? serializedStoreState.Deserialize<string>()
                : features?.TryGet<VectorChatMessageStoreThreadDbKeyFeature>(out var threadDbKeyFeature) is true
                    ? threadDbKeyFeature.ThreadDbKey
                    : Guid.NewGuid().ToString("N");
        }

        public string? ThreadDbKey { get; }

        public override async Task AddMessagesAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
        {
            var collection = this._vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
            await collection.EnsureCollectionExistsAsync(cancellationToken);

            await collection.UpsertAsync(messages.Select(x => new ChatHistoryItem()
            {
                Key = this.ThreadDbKey + (string.IsNullOrWhiteSpace(x.MessageId) ? Guid.NewGuid().ToString("N") : x.MessageId),
                Timestamp = DateTimeOffset.UtcNow,
                ThreadId = this.ThreadDbKey,
                SerializedMessage = JsonSerializer.Serialize(x),
                MessageText = x.Text
            }), cancellationToken);
        }

        public override async Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken = default)
        {
            var collection = this._vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
            await collection.EnsureCollectionExistsAsync(cancellationToken);

            var records = await collection
                .GetAsync(
                    x => x.ThreadId == this.ThreadDbKey, 10,
                    new() { OrderBy = x => x.Descending(y => y.Timestamp) },
                    cancellationToken)
                .ToListAsync(cancellationToken);

            var messages = records.ConvertAll(x => JsonSerializer.Deserialize<ChatMessage>(x.SerializedMessage!)!)
;
            messages.Reverse();
            return messages;
        }

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null) =>
            // We have to serialize the thread id, so that on deserialization we can retrieve the messages using the same thread id.
            JsonSerializer.SerializeToElement(this.ThreadDbKey);

        /// <summary>
        /// The data structure used to store chat history items in the vector store.
        /// </summary>
        private sealed class ChatHistoryItem
        {
            [VectorStoreKey]
            public string? Key { get; set; }

            [VectorStoreData]
            public string? ThreadId { get; set; }

            [VectorStoreData]
            public DateTimeOffset? Timestamp { get; set; }

            [VectorStoreData]
            public string? SerializedMessage { get; set; }

            [VectorStoreData]
            public string? MessageText { get; set; }
        }
    }
}
