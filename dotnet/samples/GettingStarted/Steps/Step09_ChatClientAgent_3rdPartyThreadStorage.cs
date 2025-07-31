// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.VectorData;
using Microsoft.SemanticKernel.Connectors.InMemory;

namespace Steps;

/// <summary>
/// Demonstrates how to store the chat history of a thread in a 3rd party store when using <see cref="ChatClientAgent"/>.
/// </summary>
public sealed class Step09_ChatClientAgent_3rdPartyThreadStorage(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    /// <summary>
    /// Demonstrate storage of the chat history of a thread in a 3rd party store when using <see cref="ChatClientAgent"/>.
    /// </summary>
    /// <remarks>
    /// Note that this is only supported for services that do not already store the chat history in their own service.
    /// </remarks>
    [Theory]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIResponses_InMemoryMessageThread)]
    public async Task ThirdPartyStorageThread(ChatClientProviders provider)
    {
        var inMemoryVectorStore = new InMemoryVectorStore();

        // Define the options for the chat client agent.
        var agentOptions = new ChatClientAgentOptions
        {
            Name = JokerName,
            Instructions = JokerInstructions,

            // Get chat options based on the store type, if needed.
            ChatOptions = base.GetChatOptions(provider),

            ChatMessageStoreFactory = () =>
            {
                // Create a new chat message store for this agent that stores the messages in a vector store.
                // Each thread must get its own copy of the VectorChatMessageStore, since the store
                // also contains the id that the thread is stored under.
                return new VectorChatMessageStore(inMemoryVectorStore);
            }
        };

        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider, agentOptions);

        // Define the agent
        var agent = new ChatClientAgent(chatClient, agentOptions);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));

        // Serialize the thread state, so it can be stored for later use.
        // Since the chat history is stored in the vector store, the serialized there
        // only contains the guid that the messages are stored under in the vector store.
        JsonElement serializedThread = await thread.SerializeAsync();

        // The serialized thread can now be saved to a database, file, or any other storage mechanism
        // and loaded again later.

        // Deserialize the thread state after loading from storage.
        AgentThread resumedThread = await agent.DeserializeThreadAsync(serializedThread);

        Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate, and add some emojis to the joke.", resumedThread));
    }

    /// <summary>
    /// A sample implementation of <see cref="IChatMessageStore"/> that stores chat messages in a vector store.
    /// </summary>
    /// <param name="vectorStore">The vector store to store the messages in.</param>
    private sealed class VectorChatMessageStore(VectorStore vectorStore) : IChatMessageStore
    {
        private string? _threadId;

        public string? ThreadId => this._threadId;

        public async Task AddMessagesAsync(IReadOnlyCollection<ChatMessage> messages, CancellationToken cancellationToken)
        {
            this._threadId ??= Guid.NewGuid().ToString();

            var collection = vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
            await collection.EnsureCollectionExistsAsync(cancellationToken);

            await collection.UpsertAsync(messages.Select(x => new ChatHistoryItem()
            {
                Key = this._threadId + x.MessageId,
                Timestamp = DateTimeOffset.UtcNow,
                ThreadId = this._threadId,
                SerializedMessage = JsonSerializer.Serialize(x),
                MessageText = x.Text
            }), cancellationToken);
        }

        public async Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken)
        {
            var collection = vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
            await collection.EnsureCollectionExistsAsync(cancellationToken);

            var records = await collection
                .GetAsync(
                    x => x.ThreadId == this._threadId, 10,
                    new() { OrderBy = x => x.Descending(y => y.Timestamp) },
                    cancellationToken)
                .ToListAsync(cancellationToken);

            var messages = records
                .Select(x => JsonSerializer.Deserialize<ChatMessage>(x.SerializedMessage!)!)
                .ToList();
            messages.Reverse();
            return messages;
        }

        public ValueTask<JsonElement?> SerializeStateAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            // We have to serialize the thread id, so that on deserialization we can retrieve the messages using the same thread id.
            return new ValueTask<JsonElement?>(JsonSerializer.SerializeToElement(this._threadId));
        }

        public ValueTask DeserializeStateAsync(JsonElement? serializedStoreState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            // Here we can deserialize the thread id so that we can access the same messages as before the suspension.
            this._threadId = JsonSerializer.Deserialize<string>((JsonElement)serializedStoreState!);
            return new ValueTask();
        }

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
