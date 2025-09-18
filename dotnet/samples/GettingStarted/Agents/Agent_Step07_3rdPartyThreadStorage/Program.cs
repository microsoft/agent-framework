// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CA1869 // Cache and reuse 'JsonSerializerOptions' instances

// This sample shows how to create and use a simple AI agent with a conversation that can be persisted to disk.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.VectorData;
using Microsoft.SemanticKernel.Connectors.InMemory;
using OpenAI;
using SampleApp;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";

// Create a vector store to store the chat messages in.
// Replace this with a vector store implementation of your choice if you want to persist the chat history to disk.
VectorStore vectorStore = new InMemoryVectorStore();

// Create the agent
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
     .GetChatClient(deploymentName)
     .CreateAIAgent(new ChatClientAgentOptions
     {
         Name = JokerName,
         Instructions = JokerInstructions,
         ChatMessageStoreFactory = ctx =>
         {
             // Create a new chat message store for this agent that stores the messages in a vector store.
             // Each thread must get its own copy of the VectorChatMessageStore, since the store
             // also contains the id that the thread is stored under.
             return new VectorChatMessageStore(vectorStore, ctx.SerializedState, ctx.JsonSerializerOptions);
         }
     });

// Start a new thread for the agent conversation.
AgentThread thread = agent.GetNewThread();

// Run the agent with the thread that stores conversation history in the vector store.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));

// Serialize the thread state, so it can be stored for later use.
// Since the chat history is stored in the vector store, the serialized thread
// only contains the guid that the messages are stored under in the vector store.
JsonElement serializedThread = await thread.SerializeAsync();

Console.WriteLine("\n--- Serialized thread ---\n");
Console.WriteLine(JsonSerializer.Serialize(serializedThread, new JsonSerializerOptions { WriteIndented = true }));

// The serialized thread can now be saved to a database, file, or any other storage mechanism
// and loaded again later.

// Deserialize the thread state after loading from storage.
AgentThread resumedThread = agent.DeserializeThread(serializedThread);

// Run the agent with the thread that stores conversation history in the vector store a second time.
Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate, and add some emojis to the joke.", resumedThread));

namespace SampleApp
{
    /// <summary>
    /// A sample implementation of <see cref="IChatMessageStore"/> that stores chat messages in a vector store.
    /// </summary>
    internal sealed class VectorChatMessageStore : IChatMessageStore
    {
        private string? _threadId;
        private readonly VectorStore _vectorStore;

        public VectorChatMessageStore(VectorStore vectorStore, JsonElement serializedStoreState, JsonSerializerOptions? jsonSerializerOptions = null)
        {
            this._vectorStore = vectorStore ?? throw new ArgumentNullException(nameof(vectorStore));

            if (serializedStoreState.ValueKind is JsonValueKind.String)
            {
                // Here we can deserialize the thread id so that we can access the same messages as before the suspension.
                this._threadId = serializedStoreState.Deserialize<string>();
            }
        }

        public async Task AddMessagesAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken)
        {
            this._threadId ??= Guid.NewGuid().ToString();

            var collection = this._vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
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
            var collection = this._vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
            await collection.EnsureCollectionExistsAsync(cancellationToken);

            var records = await collection
                .GetAsync(
                    x => x.ThreadId == this._threadId, 10,
                    new() { OrderBy = x => x.Descending(y => y.Timestamp) },
                    cancellationToken)
                .ToListAsync(cancellationToken);

            var messages = records.ConvertAll(x => JsonSerializer.Deserialize<ChatMessage>(x.SerializedMessage!)!)
;
            messages.Reverse();
            return messages;
        }

        public ValueTask<JsonElement?> SerializeStateAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            // We have to serialize the thread id, so that on deserialization we can retrieve the messages using the same thread id.
            new(JsonSerializer.SerializeToElement(this._threadId));

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
