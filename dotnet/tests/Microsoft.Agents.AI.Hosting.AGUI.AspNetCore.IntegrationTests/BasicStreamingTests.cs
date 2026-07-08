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
using FluentAssertions;
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
        session.Should().NotBeNull();

        updates.Should().NotBeEmpty();
        updates.Should().AllSatisfy(u => u.Role.Should().Be(ChatRole.Assistant));

        // Verify assistant response message
        AgentResponse response = updates.ToAgentResponse();
        response.Messages.Should().HaveCount(1);
        response.Messages[0].Role.Should().Be(ChatRole.Assistant);
        response.Messages[0].Text.Should().Be("Hello from fake agent!");
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
        updates.Should().NotBeEmpty();
        updates[0].ResponseId.Should().NotBeNullOrEmpty();
        ChatResponseUpdate firstUpdate = updates[0].AsChatResponseUpdate();
        // The AG-UI thread id is surfaced on the RUN_STARTED event (the new AGUI.Client keeps the
        // client stateless and never populates ChatResponseUpdate.ConversationId).
        string? threadId = (firstUpdate.RawRepresentation as RunStartedEvent)?.ThreadId;
        string? runId = updates[0].ResponseId;
        threadId.Should().NotBeNullOrEmpty();
        runId.Should().NotBeNullOrEmpty();

        // Should have received text updates
        updates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));

        // All text content updates should have the same message ID
        List<AgentResponseUpdate> textUpdates = updates.Where(u => !string.IsNullOrEmpty(u.Text)).ToList();
        textUpdates.Should().NotBeEmpty();
        string? firstMessageId = textUpdates.FirstOrDefault()?.MessageId;
        firstMessageId.Should().NotBeNullOrEmpty();
        textUpdates.Should().AllSatisfy(u => u.MessageId.Should().Be(firstMessageId));

        // RunFinished should be the last update
        AgentResponseUpdate lastUpdate = updates[^1];
        lastUpdate.ResponseId.Should().Be(runId);
        ChatResponseUpdate lastChatUpdate = lastUpdate.AsChatResponseUpdate();
        // The stateless client never populates ChatResponseUpdate.ConversationId; thread identity stays
        // on the AG-UI wire events instead, so verify the RUN_FINISHED event carries the same ids.
        lastChatUpdate.ConversationId.Should().BeNull();
        RunFinishedEvent? runFinished = updates
            .Select(u => u.AsChatResponseUpdate().RawRepresentation as RunFinishedEvent)
            .FirstOrDefault(e => e is not null);
        runFinished.Should().NotBeNull();
        runFinished!.ThreadId.Should().Be(threadId);
        runFinished.RunId.Should().Be(runId);
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
        response.Messages.Should().NotBeEmpty();
        response.Messages.Should().Contain(m => m.Role == ChatRole.Assistant);
        response.Messages.Should().Contain(m => m.Text == "Hello from fake agent!");
    }

    [Fact]
    public async Task MultiTurnConversationPreservesAllMessagesInSessionAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        var chatClient = new AGUIChatClient(new(this._client!, ""));
        AIAgent agent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentSession chatClientSession = (ChatClientAgentSession)await agent.CreateSessionAsync();
        ChatMessage firstUserMessage = new(ChatRole.User, "First question");

        // Act - First turn
        List<AgentResponseUpdate> firstTurnUpdates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([firstUserMessage], chatClientSession, new AgentRunOptions(), CancellationToken.None))
        {
            firstTurnUpdates.Add(update);
        }

        // Assert first turn completed
        firstTurnUpdates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));

        // Act - Second turn with another message
        ChatMessage secondUserMessage = new(ChatRole.User, "Second question");
        List<AgentResponseUpdate> secondTurnUpdates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([secondUserMessage], chatClientSession, new AgentRunOptions(), CancellationToken.None))
        {
            secondTurnUpdates.Add(update);
        }

        // Assert second turn completed
        secondTurnUpdates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));

        // Verify first turn assistant response
        AgentResponse firstResponse = firstTurnUpdates.ToAgentResponse();
        firstResponse.Messages.Should().HaveCount(1);
        firstResponse.Messages[0].Role.Should().Be(ChatRole.Assistant);
        firstResponse.Messages[0].Text.Should().Be("Hello from fake agent!");

        // Verify second turn assistant response
        AgentResponse secondResponse = secondTurnUpdates.ToAgentResponse();
        secondResponse.Messages.Should().HaveCount(1);
        secondResponse.Messages[0].Role.Should().Be(ChatRole.Assistant);
        secondResponse.Messages[0].Text.Should().Be("Hello from fake agent!");
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
        textUpdates.Should().NotBeEmpty();

        // Extract unique message IDs
        List<string> messageIds = textUpdates.Select(u => u.MessageId).Where(id => !string.IsNullOrEmpty(id)).Distinct().ToList()!;
        messageIds.Should().HaveCountGreaterThan(1, "agent should send multiple messages");

        // Verify assistant messages from updates
        AgentResponse response = updates.ToAgentResponse();
        response.Messages.Should().HaveCountGreaterThan(1);
        response.Messages.Should().AllSatisfy(m => m.Role.Should().Be(ChatRole.Assistant));
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
        updates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));
        updates.Should().Contain(u => u.Role == ChatRole.Assistant);

        // Verify assistant response message
        AgentResponse response = updates.ToAgentResponse();
        response.Messages.Should().HaveCount(1);
        response.Messages[0].Role.Should().Be(ChatRole.Assistant);
        response.Messages[0].Text.Should().Be("Hello from fake agent!");
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
        malformedResponse.StatusCode.Should().Be(System.Net.HttpStatusCode.BadRequest);
        emptyResponse.StatusCode.Should().Be(System.Net.HttpStatusCode.BadRequest);
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
