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
using AGUI.Server;
using FluentAssertions;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests;

public sealed class SharedStateTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _client;

    [Fact]
    public async Task StateSnapshot_IsSurfacedAsRawStateSnapshotEventAsync()
    {
        // Arrange
        var fakeAgent = new FakeStateAgent();
        await this.SetupTestServerAsync(fakeAgent);
        AIAgent agent = this.CreateAgent();
        ChatClientAgentSession session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        // The AG-UI thread state travels on RunAgentInput.State, supplied to the stateless client via
        // RawRepresentationFactory. The agent echoes it back as a STATE_SNAPSHOT event which the client
        // surfaces as ChatResponseUpdate.RawRepresentation (issue #4869: no DataContent / ConversationId).
        var initialState = JsonSerializer.SerializeToElement(new { counter = 42, status = "active" });
        ChatMessage userMessage = new(ChatRole.User, "update state");

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([userMessage], session, StateRunOptions(initialState), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - the state snapshot is surfaced as a StateSnapshotEvent raw representation.
        updates.Should().NotBeEmpty();

        StateSnapshotEvent? snapshot = FindStateSnapshot(updates);
        snapshot.Should().NotBeNull("should receive a STATE_SNAPSHOT event");
        snapshot!.Snapshot.GetProperty("counter").GetInt32().Should().Be(43, "state should be incremented");
        snapshot.Snapshot.GetProperty("status").GetString().Should().Be("active");
    }

    [Fact]
    public async Task StateSnapshot_UpdateHasAssistantRoleAndNoConversationIdAsync()
    {
        // Arrange
        var fakeAgent = new FakeStateAgent();
        await this.SetupTestServerAsync(fakeAgent);
        AIAgent agent = this.CreateAgent();
        ChatClientAgentSession session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        var initialState = JsonSerializer.SerializeToElement(new { step = 1 });
        ChatMessage userMessage = new(ChatRole.User, "process");

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([userMessage], session, StateRunOptions(initialState), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - the state update carries the StateSnapshotEvent and the stateless client leaves
        // ConversationId unset (state identity stays on the AG-UI wire events).
        AgentResponseUpdate? stateUpdate = updates
            .FirstOrDefault(u => u.AsChatResponseUpdate().RawRepresentation is StateSnapshotEvent);
        stateUpdate.Should().NotBeNull();

        ChatResponseUpdate chatUpdate = stateUpdate!.AsChatResponseUpdate();
        chatUpdate.RawRepresentation.Should().BeOfType<StateSnapshotEvent>();
        chatUpdate.ConversationId.Should().BeNull();
        chatUpdate.Role.Should().Be(ChatRole.Assistant);
    }

    [Fact]
    public async Task ComplexState_WithNestedObjectsAndArrays_RoundTripsCorrectlyAsync()
    {
        // Arrange
        var fakeAgent = new FakeStateAgent();
        await this.SetupTestServerAsync(fakeAgent);
        AIAgent agent = this.CreateAgent();
        ChatClientAgentSession session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        JsonElement complexState = JsonDocument.Parse(
            """{"sessionId":"test-123","nested":{"value":"test","count":10},"array":[1,2,3],"tags":["tag1","tag2"]}""").RootElement.Clone();
        ChatMessage userMessage = new(ChatRole.User, "process complex state");

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([userMessage], session, StateRunOptions(complexState), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        StateSnapshotEvent? snapshot = FindStateSnapshot(updates);
        snapshot.Should().NotBeNull();

        JsonElement receivedState = snapshot!.Snapshot;
        receivedState.GetProperty("sessionId").GetString().Should().Be("test-123");
        receivedState.GetProperty("nested").GetProperty("count").GetInt32().Should().Be(10);
        receivedState.GetProperty("array").GetArrayLength().Should().Be(3);
        receivedState.GetProperty("tags").GetArrayLength().Should().Be(2);
    }

    [Fact]
    public async Task StateSnapshot_CanBeUsedInSubsequentRequest_ForStateRoundTripAsync()
    {
        // Arrange
        var fakeAgent = new FakeStateAgent();
        await this.SetupTestServerAsync(fakeAgent);
        AIAgent agent = this.CreateAgent();
        ChatClientAgentSession session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        var initialState = JsonSerializer.SerializeToElement(new { counter = 1, sessionId = "round-trip-test" });
        ChatMessage userMessage = new(ChatRole.User, "increment");

        List<AgentResponseUpdate> firstRoundUpdates = [];

        // Act - First round
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([userMessage], session, StateRunOptions(initialState), CancellationToken.None))
        {
            firstRoundUpdates.Add(update);
        }

        // Feed the returned state snapshot back into the second round.
        StateSnapshotEvent? firstSnapshot = FindStateSnapshot(firstRoundUpdates);
        firstSnapshot.Should().NotBeNull();
        firstSnapshot!.Snapshot.GetProperty("counter").GetInt32().Should().Be(2);

        ChatMessage secondUserMessage = new(ChatRole.User, "increment again");

        List<AgentResponseUpdate> secondRoundUpdates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([secondUserMessage], session, StateRunOptions(firstSnapshot.Snapshot), CancellationToken.None))
        {
            secondRoundUpdates.Add(update);
        }

        // Assert - Second round should have incremented counter again.
        StateSnapshotEvent? secondSnapshot = FindStateSnapshot(secondRoundUpdates);
        secondSnapshot.Should().NotBeNull();
        secondSnapshot!.Snapshot.GetProperty("counter").GetInt32().Should().Be(3, "counter should be incremented twice: 1 -> 2 -> 3");
    }

    [Fact]
    public async Task WithoutState_AgentBehavesNormally_NoStateSnapshotReturnedAsync()
    {
        // Arrange
        var fakeAgent = new FakeStateAgent();
        await this.SetupTestServerAsync(fakeAgent);
        AIAgent agent = this.CreateAgent();
        ChatClientAgentSession session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        ChatMessage userMessage = new(ChatRole.User, "hello");

        List<AgentResponseUpdate> updates = [];

        // Act - no RunAgentInput.State provided.
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([userMessage], session, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        updates.Should().NotBeEmpty();
        FindStateSnapshot(updates).Should().BeNull("should not return state snapshot when no state is provided");
        updates.Should().Contain(u => u.Contents.Any(c => c is TextContent));
    }

    [Fact]
    public async Task EmptyState_DoesNotTriggerStateHandlingAsync()
    {
        // Arrange
        var fakeAgent = new FakeStateAgent();
        await this.SetupTestServerAsync(fakeAgent);
        AIAgent agent = this.CreateAgent();
        ChatClientAgentSession session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        var emptyState = JsonSerializer.SerializeToElement(new { });
        ChatMessage userMessage = new(ChatRole.User, "hello");

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([userMessage], session, StateRunOptions(emptyState), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - empty state {} should be treated as no state.
        updates.Should().NotBeEmpty();
        FindStateSnapshot(updates).Should().BeNull("empty state should be treated as no state");
        updates.Should().Contain(u => u.Contents.Any(c => c is TextContent));
    }

    [Fact]
    public async Task NonStreamingRunAsync_WithState_ReturnsTextResponseAsync()
    {
        // Arrange
        var fakeAgent = new FakeStateAgent();
        await this.SetupTestServerAsync(fakeAgent);
        AIAgent agent = this.CreateAgent();
        ChatClientAgentSession session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        var initialState = JsonSerializer.SerializeToElement(new { counter = 5 });
        ChatMessage userMessage = new(ChatRole.User, "process");

        // Act - non-streaming run.
        AgentResponse response = await agent.RunAsync([userMessage], session, StateRunOptions(initialState), CancellationToken.None);

        // Assert - AG-UI state events are a streaming concern: the non-streaming aggregation drops the
        // content-less STATE_SNAPSHOT update (Microsoft.Extensions.AI only materializes updates that carry
        // content), so the non-streaming path surfaces the aggregated text response. The state round-trip
        // itself is verified by the streaming tests above.
        response.Should().NotBeNull();
        response.Messages.Should().NotBeEmpty();
        response.Text.Should().Contain("State processed");
    }

    private ChatClientAgent CreateAgent()
    {
        var chatClient = new AGUIChatClient(new(this._client!, ""));
        return chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
    }

    private static ChatClientAgentRunOptions StateRunOptions(JsonElement state) =>
        new()
        {
            ChatOptions = new ChatOptions
            {
                RawRepresentationFactory = _ => new RunAgentInput { State = state },
            },
        };

    private static StateSnapshotEvent? FindStateSnapshot(IEnumerable<AgentResponseUpdate> updates) =>
        updates
            .Select(u => u.AsChatResponseUpdate().RawRepresentation as StateSnapshotEvent)
            .FirstOrDefault(e => e is not null);

    private async Task SetupTestServerAsync(FakeStateAgent fakeAgent)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddAGUIServer();
        builder.WebHost.UseTestServer();

        this._app = builder.Build();

        this._app.MapAGUIServer("/agent", fakeAgent);

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

[SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated in tests")]
internal sealed class FakeStateAgent : AIAgent
{
    public override string? Description => "Agent for state testing";

    protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        return this.RunCoreStreamingAsync(messages, session, options, cancellationToken).ToAgentResponseAsync(cancellationToken);
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Recover the originating AG-UI input from the request options (set by the hosting layer).
        if (options is ChatClientAgentRunOptions { ChatOptions: { } chatOptions } &&
            chatOptions.TryGetRunAgentInput(out RunAgentInput? agentInput) &&
            agentInput.State is { ValueKind: JsonValueKind.Object } state &&
            HasProperties(state))
        {
            Dictionary<string, object?> modifiedState = [];
            foreach (JsonProperty prop in state.EnumerateObject())
            {
                if (prop.Name == "counter" && prop.Value.ValueKind == JsonValueKind.Number)
                {
                    modifiedState[prop.Name] = prop.Value.GetInt32() + 1;
                }
                else if (prop.Value.ValueKind == JsonValueKind.Number)
                {
                    modifiedState[prop.Name] = prop.Value.GetInt32();
                }
                else if (prop.Value.ValueKind == JsonValueKind.String)
                {
                    modifiedState[prop.Name] = prop.Value.GetString();
                }
                else if (prop.Value.ValueKind is JsonValueKind.Object or JsonValueKind.Array)
                {
                    modifiedState[prop.Name] = prop.Value;
                }
            }

            // Emit the modified state as an AG-UI STATE_SNAPSHOT event. An AIAgent surfaces AG-UI raw
            // events by wrapping a ChatResponseUpdate (whose RawRepresentation is the event) so the
            // AgentResponseUpdate -> ChatResponseUpdate bridge forwards it to the server's event stream.
            JsonElement snapshot = JsonSerializer.SerializeToElement(modifiedState);
            yield return new AgentResponseUpdate
            {
                Role = ChatRole.Assistant,
                RawRepresentation = new ChatResponseUpdate
                {
                    Role = ChatRole.Assistant,
                    RawRepresentation = new StateSnapshotEvent { Snapshot = snapshot }
                }
            };
        }

        // Always return a text response.
        string messageId = Guid.NewGuid().ToString("N");
        yield return new AgentResponseUpdate
        {
            MessageId = messageId,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("State processed")]
        };

        await Task.CompletedTask;
    }

    private static bool HasProperties(JsonElement element)
    {
        foreach (JsonProperty _ in element.EnumerateObject())
        {
            return true;
        }

        return false;
    }

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
