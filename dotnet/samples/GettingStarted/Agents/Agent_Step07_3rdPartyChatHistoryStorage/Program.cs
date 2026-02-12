// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CA1869 // Cache and reuse 'JsonSerializerOptions' instances

// This sample shows how to create and use a simple AI agent with custom ChatHistoryProvider that stores chat history in a custom storage location.
// The state of the custom ChatHistoryProvider (SessionDbKey) is stored with the agent session, so that when the session is resumed later,
// the chat history can be retrieved from the custom storage location.

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

// Create the agent
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { Instructions = "You are good at telling jokes." },
        Name = "Joker",
        ChatHistoryProviderFactory = (ctx, ct) => new ValueTask<ChatHistoryProvider>(
            // Create a new ChatHistoryProvider for this agent that stores chat history in a vector store.
            // Each session must get its own copy of the VectorChatHistoryProvider, since the provider
            // also contains the id that the chat history is stored under.
            new VectorChatHistoryProvider(vectorStore, ctx.SerializedState, ctx.JsonSerializerOptions))
    });

// Start a new session for the agent conversation.
AgentSession session = await agent.CreateSessionAsync();

// Run the agent with the session that stores chat history in the vector store.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));

// Serialize the session state, so it can be stored for later use.
// Since the chat history is stored in the vector store, the serialized session
// only contains the guid that the messages are stored under in the vector store.
JsonElement serializedSession = await agent.SerializeSessionAsync(session);

Console.WriteLine("\n--- Serialized session ---\n");
Console.WriteLine(JsonSerializer.Serialize(serializedSession, new JsonSerializerOptions { WriteIndented = true }));

// The serialized session can now be saved to a database, file, or any other storage mechanism
// and loaded again later.

// Deserialize the session state after loading from storage.
AgentSession resumedSession = await agent.DeserializeSessionAsync(serializedSession);

// Run the agent with the session that stores chat history in the vector store a second time.
Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate, and add some emojis to the joke.", resumedSession));

// We can access the VectorChatHistoryProvider via the session's GetService method if we need to read the key under which chat history is stored.
var chatHistoryProvider = resumedSession.GetService<VectorChatHistoryProvider>()!;
Console.WriteLine($"\nSession is stored in vector store under key: {chatHistoryProvider.SessionDbKey}");

namespace SampleApp
{
    /// <summary>
    /// A sample implementation of <see cref="ChatHistoryProvider"/> that stores chat history in a vector store.
    /// </summary>
    internal sealed class VectorChatHistoryProvider : ChatHistoryProvider
    {
        private readonly VectorStore _vectorStore;

        public VectorChatHistoryProvider(VectorStore vectorStore, JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null)
        {
            this._vectorStore = vectorStore ?? throw new ArgumentNullException(nameof(vectorStore));

            if (serializedState.ValueKind is JsonValueKind.String)
            {
                // Here we can deserialize the session id so that we can access the same messages as before the suspension.
                this.SessionDbKey = serializedState.Deserialize<string>();
            }
        }

        public string? SessionDbKey { get; private set; }

        protected override async ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            var collection = this._vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
            await collection.EnsureCollectionExistsAsync(cancellationToken);

            var records = await collection
                .GetAsync(
                    x => x.SessionId == this.SessionDbKey, 10,
                    new() { OrderBy = x => x.Descending(y => y.Timestamp) },
                    cancellationToken)
                .ToListAsync(cancellationToken);

            var messages = records.ConvertAll(x => JsonSerializer.Deserialize<ChatMessage>(x.SerializedMessage!)!)
;
            messages.Reverse();
            return messages;
        }

        protected override async ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            // Don't store messages if the request failed.
            if (context.InvokeException is not null)
            {
                return;
            }

            this.SessionDbKey ??= Guid.NewGuid().ToString("N");

            var collection = this._vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
            await collection.EnsureCollectionExistsAsync(cancellationToken);

            // Add both request and response messages to the store
            // Optionally messages produced by the AIContextProvider can also be persisted (not shown).
            var allNewMessages = context.RequestMessages.Concat(context.ResponseMessages ?? []);

            await collection.UpsertAsync(allNewMessages.Select(x => new ChatHistoryItem()
            {
                Key = this.SessionDbKey + x.MessageId,
                Timestamp = DateTimeOffset.UtcNow,
                SessionId = this.SessionDbKey,
                SerializedMessage = JsonSerializer.Serialize(x),
                MessageText = x.Text
            }), cancellationToken);
        }

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null) =>
            // We have to serialize the session id, so that on deserialization we can retrieve the messages using the same session id.
            JsonSerializer.SerializeToElement(this.SessionDbKey);

        /// <summary>
        /// The data structure used to store chat history items in the vector store.
        /// </summary>
        private sealed class ChatHistoryItem
        {
            [VectorStoreKey]
            public string? Key { get; set; }

            [VectorStoreData]
            public string? SessionId { get; set; }

            [VectorStoreData]
            public DateTimeOffset? Timestamp { get; set; }

            [VectorStoreData]
            public string? SerializedMessage { get; set; }

            [VectorStoreData]
            public string? MessageText { get; set; }
        }
    }
}
