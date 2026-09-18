// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using AGUI.Abstractions;
using AGUI.Client;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests;

public sealed class BasicStreamingTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _client;

    [Fact]
    public async Task ClientReceivesStreamedAssistantMessageAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        var chatClient = new AGUIChatClient(new(this._client!, ""));
        AIAgent agent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentSession? session = (ChatClientAgentSession)await agent.CreateSessionAsync();
        ChatMessage userMessage = new(ChatRole.User, "hello");

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([userMessage], session, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        Assert.NotNull(session);

        Assert.NotEmpty(updates);
        Assert.All(updates, u => Assert.Equal(ChatRole.Assistant, u.Role));

        // Verify assistant response message
        AgentResponse response = updates.ToAgentResponse();
        ChatMessage responseMessage = Assert.Single(response.Messages);
        Assert.Equal(ChatRole.Assistant, responseMessage.Role);
        Assert.Equal("Hello from fake agent!", responseMessage.Text);
    }

    [Fact]
    public async Task ClientReceivesRunLifecycleEventsAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        var chatClient = new AGUIChatClient(new(this._client!, ""));
        AIAgent agent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentSession? session = (ChatClientAgentSession)await agent.CreateSessionAsync();
        ChatMessage userMessage = new(ChatRole.User, "test");

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([userMessage], session, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - RunStarted should be the first update
        Assert.NotEmpty(updates);
        Assert.False(string.IsNullOrEmpty(updates[0].ResponseId));
        ChatResponseUpdate firstUpdate = updates[0].AsChatResponseUpdate();
        // The AG-UI thread id is surfaced on the RUN_STARTED event (the new AGUI.Client keeps the
        // client stateless and never populates ChatResponseUpdate.ConversationId).
        string? threadId = (firstUpdate.RawRepresentation as RunStartedEvent)?.ThreadId;
        string? runId = updates[0].ResponseId;
        Assert.False(string.IsNullOrEmpty(threadId));
        Assert.False(string.IsNullOrEmpty(runId));

        // Should have received text updates
        Assert.Contains(updates, u => !string.IsNullOrEmpty(u.Text));

        // All text content updates should have the same message ID
        List<AgentResponseUpdate> textUpdates = updates.Where(u => !string.IsNullOrEmpty(u.Text)).ToList();
        Assert.NotEmpty(textUpdates);
        string? firstMessageId = textUpdates.FirstOrDefault()?.MessageId;
        Assert.False(string.IsNullOrEmpty(firstMessageId));
        Assert.All(textUpdates, u => Assert.Equal(firstMessageId, u.MessageId));

        // RunFinished should be the last update
        AgentResponseUpdate lastUpdate = updates[^1];
        Assert.Equal(runId, lastUpdate.ResponseId);
        ChatResponseUpdate lastChatUpdate = lastUpdate.AsChatResponseUpdate();
        // The stateless client never populates ChatResponseUpdate.ConversationId; thread identity stays
        // on the AG-UI wire events instead, so verify the RUN_FINISHED event carries the same ids.
        Assert.Null(lastChatUpdate.ConversationId);
        RunFinishedEvent? runFinished = updates
            .Select(u => u.AsChatResponseUpdate().RawRepresentation as RunFinishedEvent)
            .FirstOrDefault(e => e is not null);
        Assert.NotNull(runFinished);
        Assert.Equal(threadId, runFinished!.ThreadId);
        Assert.Equal(runId, runFinished.RunId);
    }

    [Fact]
    public async Task RunAsyncAggregatesStreamingUpdatesAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        var chatClient = new AGUIChatClient(new(this._client!, ""));
        AIAgent agent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentSession? session = (ChatClientAgentSession)await agent.CreateSessionAsync();
        ChatMessage userMessage = new(ChatRole.User, "hello");

        // Act
        AgentResponse response = await agent.RunAsync([userMessage], session, new AgentRunOptions(), CancellationToken.None);

        // Assert
        Assert.NotEmpty(response.Messages);
        Assert.Contains(response.Messages, m => m.Role == ChatRole.Assistant);
        Assert.Contains(response.Messages, m => m.Text == "Hello from fake agent!");
    }

    [Fact]
    public async Task AGUIChatClientBackedAgentUsesLocalChatHistoryAcrossTurnsAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        var chatClient = new AGUIChatClient(new(this._client!, ""));
        ChatClientAgent agent = new(chatClient, instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentSession chatClientSession = (ChatClientAgentSession)await agent.CreateSessionAsync();
        ChatMessage firstUserMessage = new(ChatRole.User, "First question");

        // Act - First turn
        List<AgentResponseUpdate> firstTurnUpdates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([firstUserMessage], chatClientSession, new AgentRunOptions(), CancellationToken.None))
        {
            firstTurnUpdates.Add(update);
        }

        // Assert first turn completed
        Assert.Contains(firstTurnUpdates, u => !string.IsNullOrEmpty(u.Text));
        Assert.All(firstTurnUpdates, u => Assert.Null(u.AsChatResponseUpdate().ConversationId));
        Assert.Null(chatClientSession.ConversationId);

        // Act - Second turn with another message
        ChatMessage secondUserMessage = new(ChatRole.User, "Second question");
        List<AgentResponseUpdate> secondTurnUpdates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([secondUserMessage], chatClientSession, new AgentRunOptions(), CancellationToken.None))
        {
            secondTurnUpdates.Add(update);
        }

        // Assert second turn completed
        Assert.Contains(secondTurnUpdates, u => !string.IsNullOrEmpty(u.Text));
        Assert.All(secondTurnUpdates, u => Assert.Null(u.AsChatResponseUpdate().ConversationId));
        Assert.Null(chatClientSession.ConversationId);

        // Verify the local provider retained both turns.
        InMemoryChatHistoryProvider historyProvider = Assert.IsType<InMemoryChatHistoryProvider>(agent.ChatHistoryProvider);
        List<ChatMessage> history = historyProvider.GetMessages(chatClientSession);
        Assert.Equal(4, history.Count);
        Assert.Equal(ChatRole.User, history[0].Role);
        Assert.Equal("First question", history[0].Text);
        Assert.Equal(ChatRole.Assistant, history[1].Role);
        Assert.Equal("Hello from fake agent!", history[1].Text);
        Assert.Equal(ChatRole.User, history[2].Role);
        Assert.Equal("Second question", history[2].Text);
        Assert.Equal(ChatRole.Assistant, history[3].Role);
        Assert.Equal("Hello from fake agent!", history[3].Text);

        // Verify first turn assistant response.
        AgentResponse firstResponse = firstTurnUpdates.ToAgentResponse();
        ChatMessage firstResponseMessage = Assert.Single(firstResponse.Messages);
        Assert.Equal(ChatRole.Assistant, firstResponseMessage.Role);
        Assert.Equal("Hello from fake agent!", firstResponseMessage.Text);

        // Verify second turn assistant response.
        AgentResponse secondResponse = secondTurnUpdates.ToAgentResponse();
        ChatMessage secondResponseMessage = Assert.Single(secondResponse.Messages);
        Assert.Equal(ChatRole.Assistant, secondResponseMessage.Role);
        Assert.Equal("Hello from fake agent!", secondResponseMessage.Text);
    }

    [Fact]
    public async Task AgentSendsMultipleMessagesInOneTurnAsync()
    {
        // Arrange
        await this.SetupTestServerAsync(useMultiMessageAgent: true);
        var chatClient = new AGUIChatClient(new(this._client!, ""));
        AIAgent agent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentSession chatClientSession = (ChatClientAgentSession)await agent.CreateSessionAsync();
        ChatMessage userMessage = new(ChatRole.User, "Tell me a story");

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([userMessage], chatClientSession, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - Should have received text updates with different message IDs
        List<AgentResponseUpdate> textUpdates = updates.Where(u => !string.IsNullOrEmpty(u.Text)).ToList();
        Assert.NotEmpty(textUpdates);

        // Extract unique message IDs
        List<string> messageIds = textUpdates.Select(u => u.MessageId).Where(id => !string.IsNullOrEmpty(id)).Distinct().ToList()!;
        Assert.True(messageIds.Count > 1);

        // Verify assistant messages from updates
        AgentResponse response = updates.ToAgentResponse();
        Assert.True(response.Messages.Count > 1);
        Assert.All(response.Messages, m => Assert.Equal(ChatRole.Assistant, m.Role));
    }

    [Fact]
    public async Task UserSendsMultipleMessagesAtOnceAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        var chatClient = new AGUIChatClient(new(this._client!, ""));
        AIAgent agent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentSession chatClientSession = (ChatClientAgentSession)await agent.CreateSessionAsync();

        // Multiple user messages sent in one turn
        ChatMessage[] userMessages =
        [
            new ChatMessage(ChatRole.User, "First part of question"),
            new ChatMessage(ChatRole.User, "Second part of question"),
            new ChatMessage(ChatRole.User, "Third part of question")
        ];

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(userMessages, chatClientSession, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - Should have received assistant response
        Assert.Contains(updates, u => !string.IsNullOrEmpty(u.Text));
        Assert.Contains(updates, u => u.Role == ChatRole.Assistant);

        // Verify assistant response message
        AgentResponse response = updates.ToAgentResponse();
        ChatMessage responseMessage = Assert.Single(response.Messages);
        Assert.Equal(ChatRole.Assistant, responseMessage.Role);
        Assert.Equal("Hello from fake agent!", responseMessage.Text);
    }

    [Fact]
    public async Task PostMalformedOrEmptyBody_ReturnsBadRequestAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();

        var endpoint = new Uri("http://localhost/agent");

        // Act - malformed JSON body
        using var malformed = new StringContent("{ not valid json", System.Text.Encoding.UTF8, "application/json");
        using HttpResponseMessage malformedResponse = await this._client!.PostAsync(endpoint, malformed);

        // Act - empty body
        using var empty = new StringContent(string.Empty, System.Text.Encoding.UTF8, "application/json");
        using HttpResponseMessage emptyResponse = await this._client!.PostAsync(endpoint, empty);

        // Assert - the hosting glue rejects both with 400 rather than 5xx.
        Assert.Equal(System.Net.HttpStatusCode.BadRequest, malformedResponse.StatusCode);
        Assert.Equal(System.Net.HttpStatusCode.BadRequest, emptyResponse.StatusCode);
    }

    private async Task SetupTestServerAsync(bool useMultiMessageAgent = false)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        builder.Services.AddAGUIServer();

        if (useMultiMessageAgent)
        {
            builder.Services.AddSingleton<FakeMultiMessageAgent>();
        }
        else
        {
            builder.Services.AddSingleton<FakeChatClientAgent>();
        }

        this._app = builder.Build();

        AIAgent agent = useMultiMessageAgent
            ? this._app.Services.GetRequiredService<FakeMultiMessageAgent>()
            : this._app.Services.GetRequiredService<FakeChatClientAgent>();

        this._app.MapAGUIServer("/agent", agent);

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._client = testServer.CreateClient();
        this._client.BaseAddress = new Uri("http://localhost/agent");
    }

    public async ValueTask DisposeAsync()
    {
        this._client?.Dispose();
        if (this._app != null)
        {
            await this._app.DisposeAsync();
        }
    }
}

[SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated via dependency injection")]
internal sealed class FakeChatClientAgent : AIAgent
{
    protected override string? IdCore => "fake-agent";

    public override string? Description => "A fake agent for testing";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new FakeAgentSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(serializedState.Deserialize<FakeAgentSession>(jsonSerializerOptions)!);

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => throw new NotImplementedException();

    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in this.RunStreamingAsync(messages, session, options, cancellationToken).ConfigureAwait(false))
        {
            updates.Add(update);
        }

        return updates.ToAgentResponse();
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string messageId = Guid.NewGuid().ToString("N");

        // Simulate streaming a deterministic response
        foreach (string chunk in new[] { "Hello", " ", "from", " ", "fake", " ", "agent", "!" })
        {
            yield return new AgentResponseUpdate
            {
                MessageId = messageId,
                Role = ChatRole.Assistant,
                Contents = [new TextContent(chunk)]
            };

            await Task.Yield();
        }
    }

    private sealed class FakeAgentSession : AgentSession
    {
        public FakeAgentSession()
        {
        }

        [JsonConstructor]
        public FakeAgentSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }
}

[SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated via dependency injection")]
internal sealed class FakeMultiMessageAgent : AIAgent
{
    protected override string? IdCore => "fake-multi-message-agent";

    public override string? Description => "A fake agent that sends multiple messages for testing";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new FakeAgentSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(serializedState.Deserialize<FakeAgentSession>(jsonSerializerOptions)!);

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        if (session is not FakeAgentSession fakeSession)
        {
            throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(FakeAgentSession)}' can be serialized by this agent.");
        }

        return new(JsonSerializer.SerializeToElement(fakeSession, jsonSerializerOptions));
    }

    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in this.RunStreamingAsync(messages, session, options, cancellationToken).ConfigureAwait(false))
        {
            updates.Add(update);
        }

        return updates.ToAgentResponse();
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Simulate sending first message
        string messageId1 = Guid.NewGuid().ToString("N");
        foreach (string chunk in new[] { "First", " ", "message" })
        {
            yield return new AgentResponseUpdate
            {
                MessageId = messageId1,
                Role = ChatRole.Assistant,
                Contents = [new TextContent(chunk)]
            };

            await Task.Yield();
        }

        // Simulate sending second message
        string messageId2 = Guid.NewGuid().ToString("N");
        foreach (string chunk in new[] { "Second", " ", "message" })
        {
            yield return new AgentResponseUpdate
            {
                MessageId = messageId2,
                Role = ChatRole.Assistant,
                Contents = [new TextContent(chunk)]
            };

            await Task.Yield();
        }

        // Simulate sending third message
        string messageId3 = Guid.NewGuid().ToString("N");
        foreach (string chunk in new[] { "Third", " ", "message" })
        {
            yield return new AgentResponseUpdate
            {
                MessageId = messageId3,
                Role = ChatRole.Assistant,
                Contents = [new TextContent(chunk)]
            };

            await Task.Yield();
        }
    }

    private sealed class FakeAgentSession : AgentSession
    {
        public FakeAgentSession()
        {
        }

        [JsonConstructor]
        public FakeAgentSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }

    public override object? GetService(Type serviceType, object? serviceKey = null) => null;
}
