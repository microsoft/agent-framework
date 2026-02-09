// Copyright (c) Microsoft. All rights reserved.

// Custom Chat History Storage
// Implement a custom ChatHistoryProvider that stores chat history in a vector store.
// The session state persists only the storage key, not the full message history.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/conversations

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

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

VectorStore vectorStore = new InMemoryVectorStore();

// <custom_storage>
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { Instructions = "You are good at telling jokes." },
        Name = "Joker",
        ChatHistoryProviderFactory = (ctx, ct) => new ValueTask<ChatHistoryProvider>(
            new VectorChatHistoryProvider(vectorStore, ctx.SerializedState, ctx.JsonSerializerOptions))
    });
// </custom_storage>

AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));

// Serialize — only the storage key is persisted, not the full chat history
JsonElement serializedSession = agent.SerializeSession(session);
Console.WriteLine($"\nSerialized session:\n{JsonSerializer.Serialize(serializedSession, new JsonSerializerOptions { WriteIndented = true })}");

// Resume the session
AgentSession resumedSession = await agent.DeserializeSessionAsync(serializedSession);
Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate.", resumedSession));

namespace SampleApp
{
    // <vector_chat_history_provider>
    internal sealed class VectorChatHistoryProvider : ChatHistoryProvider
    {
        private readonly VectorStore _vectorStore;

        public VectorChatHistoryProvider(VectorStore vectorStore, JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null)
        {
            _vectorStore = vectorStore;
            if (serializedState.ValueKind is JsonValueKind.String)
            {
                SessionDbKey = serializedState.Deserialize<string>();
            }
        }

        public string? SessionDbKey { get; private set; }

        public override async ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            var collection = _vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
            await collection.EnsureCollectionExistsAsync(cancellationToken);

            var records = await collection
                .GetAsync(x => x.SessionId == SessionDbKey, 10,
                    new() { OrderBy = x => x.Descending(y => y.Timestamp) }, cancellationToken)
                .ToListAsync(cancellationToken);

            var messages = records.ConvertAll(x => JsonSerializer.Deserialize<ChatMessage>(x.SerializedMessage!)!);
            messages.Reverse();
            return messages;
        }

        public override async ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            if (context.InvokeException is not null) return;

            SessionDbKey ??= Guid.NewGuid().ToString("N");

            var collection = _vectorStore.GetCollection<string, ChatHistoryItem>("ChatHistory");
            await collection.EnsureCollectionExistsAsync(cancellationToken);

            var allNewMessages = context.RequestMessages.Concat(context.ResponseMessages ?? []);
            await collection.UpsertAsync(allNewMessages.Select(x => new ChatHistoryItem
            {
                Key = SessionDbKey + x.MessageId,
                Timestamp = DateTimeOffset.UtcNow,
                SessionId = SessionDbKey,
                SerializedMessage = JsonSerializer.Serialize(x),
                MessageText = x.Text
            }), cancellationToken);
        }

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
            => JsonSerializer.SerializeToElement(SessionDbKey);

        private sealed class ChatHistoryItem
        {
            [VectorStoreKey] public string? Key { get; set; }
            [VectorStoreData] public string? SessionId { get; set; }
            [VectorStoreData] public DateTimeOffset? Timestamp { get; set; }
            [VectorStoreData] public string? SerializedMessage { get; set; }
            [VectorStoreData] public string? MessageText { get; set; }
        }
    }
    // </vector_chat_history_provider>
}
