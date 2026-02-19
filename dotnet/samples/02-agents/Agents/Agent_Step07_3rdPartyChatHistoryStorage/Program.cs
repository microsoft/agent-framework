// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CA1869 // Cache and reuse 'JsonSerializerOptions' instances

// This sample shows how to create and use a simple AI agent with custom ChatHistoryProvider that stores chat history in a custom storage location.
// The state of the custom ChatHistoryProvider (SessionDbKey) is stored in the AgentSession's StateBag, so that when the session is resumed later,
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
        // Create a new ChatHistoryProvider for this agent that stores chat history in a vector store.
        ChatHistoryProvider = new VectorChatHistoryProvider(vectorStore)
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

// We can access the VectorChatHistoryProvider via the agent's GetService method
// if we need to read the key under which chat history is stored. The key is stored
// in the session state, and therefore we need to provide the session when reading it.
var chatHistoryProvider = agent.GetService<VectorChatHistoryProvider>()!;
Console.WriteLine($"\nSession is stored in vector store under key: {chatHistoryProvider.GetSessionDbKey(resumedSession)}");

namespace SampleApp
{
    /// <summary>
    /// A sample implementation of <see cref="ChatHistoryProvider"/> that stores chat history in a vector store.
    /// State (the session DB key) is stored in the <see cref="AgentSession.StateBag"/> so it roundtrips
    /// automatically with session serialization.
    /// </summary>
    internal sealed class VectorChatHistoryProvider : ChatHistoryProvider
    {
        private readonly ProviderSessionState<State> _sessionState;
        private readonly VectorStore _vectorStore;

        public VectorChatHistoryProvider(
            VectorStore vectorStore,
            Func<AgentSession?, State>? stateInitializer = null,
            string? stateKey = null)
            : base(provideOutputMessageFilter: null, storeInputMessageFilter: null)
        {
            this._sessionState = new ProviderSessionState<State>(
                stateInitializer ?? (_ => new State(Guid.NewGuid().ToString("N"))),
                stateKey ?? this.GetType().Name);
            this._vectorStore = vectorStore ?? throw new ArgumentNullException(nameof(vectorStore));
        }

        public override string StateKey => this._sessionState.StateKey;

        public string GetSessionDbKey(AgentSession session)
            => this._sessionState.GetOrInitializeState(session).SessionDbKey;

        protected override async ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            var state = this._sessionState.GetOrInitializeState(context.Session);
            var collection = this._vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
            await collection.EnsureCollectionExistsAsync(cancellationToken);

            var records = await collection
                .GetAsync(
                    x => x.SessionId == state.SessionDbKey, 10,
                    new() { OrderBy = x => x.Descending(y => y.Timestamp) },
                    cancellationToken)
                .ToListAsync(cancellationToken);

            var messages = records.ConvertAll(x => JsonSerializer.Deserialize<ChatMessage>(x.SerializedMessage!)!);
            messages.Reverse();
            return messages;
        }

        protected override async ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            var state = this._sessionState.GetOrInitializeState(context.Session);

            var collection = this._vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
            await collection.EnsureCollectionExistsAsync(cancellationToken);

            var allNewMessages = context.RequestMessages.Concat(context.ResponseMessages ?? []);

            await collection.UpsertAsync(allNewMessages.Select(x => new ChatHistoryItem()
            {
                Key = state.SessionDbKey + x.MessageId,
                Timestamp = DateTimeOffset.UtcNow,
                SessionId = state.SessionDbKey,
                SerializedMessage = JsonSerializer.Serialize(x),
                MessageText = x.Text
            }), cancellationToken);
        }

        /// <summary>
        /// Represents the per-session state stored in the <see cref="AgentSession.StateBag"/>.
        /// </summary>
        public sealed class State
        {
            public State(string sessionDbKey)
            {
                this.SessionDbKey = sessionDbKey ?? throw new ArgumentNullException(nameof(sessionDbKey));
            }

            public string SessionDbKey { get; }
        }

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
