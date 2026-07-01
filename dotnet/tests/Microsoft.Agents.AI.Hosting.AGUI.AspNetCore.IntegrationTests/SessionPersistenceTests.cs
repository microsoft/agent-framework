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

public sealed class SessionPersistenceTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _client;

    [Fact]
    public async Task MultiTurnWithSessionStore_PersistsSessionAcrossRequestsAsync()
    {
        // Arrange - use hosting DI pattern with InMemorySessionStore.
        // FakeSessionAgent tracks turn count in session StateBag so we can verify
        // that state survives the serialization round-trip through the session store.
        await this.SetupTestServerWithSessionStoreAsync();
        var chatClient = new AGUIChatClient(new(this._client!, ""));
        AIAgent agent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentSession session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        // Act - First turn
        ChatMessage firstUserMessage = new(ChatRole.User, "First message");
        List<AgentResponseUpdate> firstTurnUpdates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([firstUserMessage], session, new AgentRunOptions(), CancellationToken.None))
        {
            firstTurnUpdates.Add(update);
        }

        // Act - Second turn (continue the same AG-UI run on the same thread).
        // The new AGUI.Client is stateless and never round-trips ConversationId. AG-UI continuation is
        // expressed on the wire with the same threadId plus a parentRunId equal to the previous turn's
        // runId. We capture both from turn 1's RUN_STARTED event and supply them to the stateless client
        // through RawRepresentationFactory, sending only the new message (the continuation subset).
        RunStartedEvent? firstRunStarted = firstTurnUpdates
            .Select(u => u.AsChatResponseUpdate().RawRepresentation as RunStartedEvent)
            .FirstOrDefault(e => e is not null);
        firstRunStarted.Should().NotBeNull();
        string threadId = firstRunStarted!.ThreadId;
        string previousRunId = firstRunStarted.RunId;
        threadId.Should().NotBeNullOrEmpty();
        previousRunId.Should().NotBeNullOrEmpty();

        ChatMessage secondUserMessage = new(ChatRole.User, "Second message");
        var continuationOptions = new ChatClientAgentRunOptions
        {
            ChatOptions = new ChatOptions
            {
                RawRepresentationFactory = _ => new RunAgentInput
                {
                    ThreadId = threadId,
                    ParentRunId = previousRunId,
                    Messages = new[] { secondUserMessage }.AsAGUIMessages().ToList(),
                },
            },
        };
        List<AgentResponseUpdate> secondTurnUpdates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([secondUserMessage], session, continuationOptions, CancellationToken.None))
        {
            secondTurnUpdates.Add(update);
        }

        // Assert - Verify turn count proves session state was persisted.
        // If session persistence were broken, both turns would return "Turn 1"
        // because a fresh session (with turn count 0) would be created each time.
        AgentResponse firstResponse = firstTurnUpdates.ToAgentResponse();
        firstResponse.Messages.Should().HaveCount(1);
        firstResponse.Messages[0].Role.Should().Be(ChatRole.Assistant);
        firstResponse.Messages[0].Text.Should().Contain("Turn 1:");

        AgentResponse secondResponse = secondTurnUpdates.ToAgentResponse();
        secondResponse.Messages.Should().HaveCount(1);
        secondResponse.Messages[0].Role.Should().Be(ChatRole.Assistant);
        secondResponse.Messages[0].Text.Should().Contain("Turn 2:");
    }

    [Fact]
    public async Task MapAGUIServer_WithAgentName_StreamsResponseCorrectlyAsync()
    {
        // Arrange - use the MapAGUIServer(agentName, pattern) overload via hosting DI
        await this.SetupTestServerWithSessionStoreAsync();
        var chatClient = new AGUIChatClient(new(this._client!, ""));
        AIAgent agent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentSession session = (ChatClientAgentSession)await agent.CreateSessionAsync();
        ChatMessage userMessage = new(ChatRole.User, "hello");

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([userMessage], session, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        updates.Should().NotBeEmpty();
        updates.Should().AllSatisfy(u => u.Role.Should().Be(ChatRole.Assistant));

        AgentResponse response = updates.ToAgentResponse();
        response.Messages.Should().HaveCount(1);
        response.Messages[0].Role.Should().Be(ChatRole.Assistant);
        response.Messages[0].Text.Should().Be("Turn 1: Hello from session agent!");
    }

    private async Task SetupTestServerWithSessionStoreAsync()
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        builder.Services.AddAGUIServer();

        // Register agent using hosting DI pattern with InMemorySessionStore
        builder.Services.AddAIAgent("session-test-agent", (_, name) => new FakeSessionAgent(name))
            .WithInMemorySessionStore(withIsolation: false);

        this._app = builder.Build();

        // Use the agentName overload of MapAGUIServer
        this._app.MapAGUIServer("session-test-agent", "/agent");

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
internal sealed class FakeSessionAgent : AIAgent
{
    private readonly string _name;

    public FakeSessionAgent(string name)
    {
        this._name = name;
    }

    protected override string? IdCore => this._name;

    public override string? Name => this._name;

    public override string? Description => "A fake agent with session support for testing";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new FakeSessionAgentSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(serializedState.Deserialize<FakeSessionAgentSession>(jsonSerializerOptions)!);

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        if (session is not FakeSessionAgentSession fakeSession)
        {
            throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent.");
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
        // Track turn count in session state to enable persistence verification.
        // If the session store works correctly, the turn count increments across requests.
        int turnCount = 1;
        if (session != null)
        {
            var counter = session.StateBag.GetValue<TurnCounter>("turnCounter");
            turnCount = (counter?.Count ?? 0) + 1;
            session.StateBag.SetValue("turnCounter", new TurnCounter { Count = turnCount });
        }

        string messageId = Guid.NewGuid().ToString("N");
        string prefix = $"Turn {turnCount}: ";

        foreach (string chunk in new[] { prefix, "Hello", " ", "from", " ", "session", " ", "agent", "!" })
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

    internal sealed class TurnCounter
    {
        public int Count { get; set; }
    }

    private sealed class FakeSessionAgentSession : AgentSession
    {
        public FakeSessionAgentSession()
        {
        }

        [JsonConstructor]
        public FakeSessionAgentSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }
}
