// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.OpenAI;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace DevUIWithSqlitePersistence.UnitTests;

public sealed class SqliteConversationDatabaseTests
{
    [Fact]
    public async Task AgentSessionAndDatabaseChatHistorySurviveRestartAsync()
    {
        // Arrange
        string path = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.db");
        try
        {
            var observed = new List<ChatMessage>();
            var firstDatabase = new SqliteConversationDatabase(path);
            var firstAgent = CreateAgent(new SqliteChatHistoryProvider(firstDatabase), observed);
            var key = new AgentSessionStoreKey("conv_1");
            AgentSession firstSession = await firstDatabase.GetOrCreateSessionAsync(firstAgent, key);
            await firstAgent.RunAsync("Remember invoice 123.", firstSession);
            await firstDatabase.SaveSessionAsync(firstAgent, key, firstSession);

            // Act
            var reopenedDatabase = new SqliteConversationDatabase(path);
            var reopenedAgent = CreateAgent(new SqliteChatHistoryProvider(reopenedDatabase), observed);
            AgentSession restoredSession = await reopenedDatabase.GetOrCreateSessionAsync(reopenedAgent, key);
            await reopenedAgent.RunAsync("Which invoice?", restoredSession);

            // Assert
            Assert.Equal(
                ["Remember invoice 123.", "reply", "Which invoice?"],
                observed.Select(message => message.Text));
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public async Task OpenAIConversationRecordsAndIndexSurviveRestartAsync()
    {
        // Arrange
        string path = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.db");
        try
        {
            var database = new SqliteConversationDatabase(path);
            var conversation = new OpenAIConversationRecord
            {
                Id = "conv_1",
                Data = JsonSerializer.SerializeToElement(new { id = "conv_1", metadata = new { agent_id = "assistant" } }),
            };
            var item = new OpenAIConversationItem
            {
                Id = "msg_1",
                Data = JsonSerializer.SerializeToElement(new { id = "msg_1", type = "message", text = "hello" }),
            };
            await database.CreateConversationAsync(conversation);
            await database.AddItemsAsync(conversation.Id, [item]);
            await database.AddConversationToAgentAsync("assistant", conversation.Id);

            // Act
            var reopened = new SqliteConversationDatabase(path);
            OpenAIConversationRecord? restoredConversation = await reopened.GetConversationAsync(conversation.Id);
            OpenAIConversationItem? restoredItem = await reopened.GetItemAsync(conversation.Id, item.Id);
            IReadOnlyList<string> conversationIds = await reopened.ListConversationIdsAsync("assistant");

            // Assert
            Assert.Equal("conv_1", restoredConversation?.Data.GetProperty("id").GetString());
            Assert.Equal("hello", restoredItem?.Data.GetProperty("text").GetString());
            Assert.Equal(["conv_1"], conversationIds);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public async Task BuiltInOpenAIHostingRestoresConversationAfterRestartAsync()
    {
        // Arrange
        string path = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.db");
        try
        {
            string conversationId;
            await using (TestHost firstHost = await CreateTestHostAsync(path))
            {
                using HttpResponseMessage createConversation = await PostJsonAsync(
                    firstHost.Client,
                    "/v1/conversations",
                    new { metadata = new { agent_id = "assistant" } });
                conversationId = (await ParseJsonAsync(createConversation)).GetProperty("id").GetString()!;

                using HttpResponseMessage firstResponse = await PostJsonAsync(
                    firstHost.Client,
                    "/v1/responses",
                    new
                    {
                        agent = new { name = "assistant" },
                        conversation = conversationId,
                        input = "Remember invoice 123.",
                        stream = false,
                    });
                Assert.True(
                    firstResponse.IsSuccessStatusCode,
                    await firstResponse.Content.ReadAsStringAsync());
            }

            // Act
            await using TestHost secondHost = await CreateTestHostAsync(path);
            using HttpResponseMessage listConversations = await secondHost.Client.GetAsync(
                new Uri("/v1/conversations?agent_id=assistant", UriKind.Relative));
            JsonElement conversations = await ParseJsonAsync(listConversations);
            using HttpResponseMessage listItems = await secondHost.Client.GetAsync(
                new Uri($"/v1/conversations/{conversationId}/items?order=asc", UriKind.Relative));
            JsonElement conversationItems = await ParseJsonAsync(listItems);
            using HttpResponseMessage secondResponse = await PostJsonAsync(
                secondHost.Client,
                "/v1/responses",
                new
                {
                    agent = new { name = "assistant" },
                    conversation = conversationId,
                    input = "Which invoice?",
                    stream = false,
                });
            Assert.True(
                secondResponse.IsSuccessStatusCode,
                await secondResponse.Content.ReadAsStringAsync());

            // Assert
            Assert.Contains(
                conversations.GetProperty("data").EnumerateArray(),
                conversation => conversation.GetProperty("id").GetString() == conversationId);
            Assert.Contains(
                conversationItems.GetProperty("data").EnumerateArray(),
                item => item.GetProperty("type").GetString() == "message"
                    && item.GetProperty("role").GetString() == "user");
            Assert.Contains(
                conversationItems.GetProperty("data").EnumerateArray(),
                item => item.GetProperty("type").GetString() == "message"
                    && item.GetProperty("role").GetString() == "assistant");
            Assert.Equal(
                ["Remember invoice 123.", "reply", "Which invoice?"],
                secondHost.ObservedMessages.Select(message => message.Text));
        }
        finally
        {
            File.Delete(path);
        }
    }

    private static ChatClientAgent CreateAgent(
        ChatHistoryProvider historyProvider,
        List<ChatMessage> observed)
    {
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) =>
            {
                observed.Clear();
                observed.AddRange(messages);
                return new ChatResponse(new ChatMessage(ChatRole.Assistant, "reply"));
            });
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) =>
                CreateStreamingResponseAsync(messages, observed, cancellationToken));

        return new ChatClientAgent(client.Object, new ChatClientAgentOptions
        {
            Name = "assistant",
            ChatHistoryProvider = historyProvider,
        });
    }

    private static async Task<TestHost> CreateTestHostAsync(string databasePath)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        var observedMessages = new List<ChatMessage>();
        var database = new SqliteConversationDatabase(databasePath);
        var historyProvider = new SqliteChatHistoryProvider(database);
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) =>
            {
                observedMessages.Clear();
                observedMessages.AddRange(messages);
                return new ChatResponse(new ChatMessage(ChatRole.Assistant, "reply"));
            });
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) =>
                CreateStreamingResponseAsync(messages, observedMessages, cancellationToken));

        builder.AddAIAgent("assistant", (_, name) =>
            new ChatClientAgent(client.Object, new ChatClientAgentOptions
            {
                Name = name,
                ChatHistoryProvider = historyProvider,
            }))
            .WithSessionStore(database, withIsolation: false);
        builder.Services.AddOpenAIResponses();
        builder.Services.AddOpenAIConversations();
        builder.Services.UseOpenAIConversationStore(database);

        WebApplication app = builder.Build();
        app.MapOpenAIResponses();
        app.MapOpenAIConversations();
        await app.StartAsync();

        TestServer server = app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer was not registered.");
        return new TestHost(app, server.CreateClient(), observedMessages);
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> CreateStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        List<ChatMessage> observedMessages,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        observedMessages.Clear();
        observedMessages.AddRange(messages);
        await Task.Yield();
        cancellationToken.ThrowIfCancellationRequested();
        yield return new ChatResponseUpdate(ChatRole.Assistant, "reply") { MessageId = "msg_reply" };
    }

    private static async Task<HttpResponseMessage> PostJsonAsync(HttpClient client, string path, object body)
    {
        using var content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
        return await client.PostAsync(new Uri(path, UriKind.Relative), content);
    }

    private static async Task<JsonElement> ParseJsonAsync(HttpResponseMessage response)
    {
        response.EnsureSuccessStatusCode();
        using JsonDocument document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        return document.RootElement.Clone();
    }

    private sealed class TestHost(
        WebApplication application,
        HttpClient client,
        List<ChatMessage> observedMessages) : IAsyncDisposable
    {
        public HttpClient Client { get; } = client;

        public List<ChatMessage> ObservedMessages { get; } = observedMessages;

        public async ValueTask DisposeAsync()
        {
            this.Client.Dispose();
            await application.DisposeAsync();
        }
    }
}
