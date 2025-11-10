// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.AGUI;
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
    public async Task StateSnapshot_IsReturnedAsDataContent_WithCorrectMediaTypeAsync()
    {
        // Arrange
        var initialState = new { counter = 42, status = "active" };
        var fakeAgent = new FakeStateAgent();

        await this.SetupTestServerAsync(fakeAgent);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread thread = (ChatClientAgentThread)agent.GetNewThread();

        string stateJson = JsonSerializer.Serialize(initialState);
        byte[] stateBytes = System.Text.Encoding.UTF8.GetBytes(stateJson);
        DataContent stateContent = new(stateBytes, "application/json");
        ChatMessage stateMessage = new(ChatRole.System, [stateContent]);
        ChatMessage userMessage = new(ChatRole.User, "update state");

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage, stateMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        updates.Should().NotBeEmpty();

        // Should receive state snapshot as DataContent with application/json media type
        AgentRunResponseUpdate? stateUpdate = updates.FirstOrDefault(u => u.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json"));
        stateUpdate.Should().NotBeNull("should receive state snapshot update");

        DataContent? dataContent = stateUpdate!.Contents.OfType<DataContent>().FirstOrDefault(dc => dc.MediaType == "application/json");
        dataContent.Should().NotBeNull();

        // Verify the state content
        string receivedJson = System.Text.Encoding.UTF8.GetString(dataContent!.Data.ToArray());
        JsonElement receivedState = JsonSerializer.Deserialize<JsonElement>(receivedJson);
        receivedState.GetProperty("counter").GetInt32().Should().Be(43, "state should be incremented");
        receivedState.GetProperty("status").GetString().Should().Be("active");
    }

    [Fact]
    public async Task StateSnapshot_HasCorrectAdditionalPropertiesAsync()
    {
        // Arrange
        var initialState = new { step = 1 };
        var fakeAgent = new FakeStateAgent();

        await this.SetupTestServerAsync(fakeAgent);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread thread = (ChatClientAgentThread)agent.GetNewThread();

        string stateJson = JsonSerializer.Serialize(initialState);
        byte[] stateBytes = System.Text.Encoding.UTF8.GetBytes(stateJson);
        DataContent stateContent = new(stateBytes, "application/json");
        ChatMessage stateMessage = new(ChatRole.System, [stateContent]);
        ChatMessage userMessage = new(ChatRole.User, "process");

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage, stateMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        AgentRunResponseUpdate? stateUpdate = updates.FirstOrDefault(u => u.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json"));
        stateUpdate.Should().NotBeNull();

        ChatResponseUpdate chatUpdate = stateUpdate!.AsChatResponseUpdate();
        chatUpdate.AdditionalProperties.Should().NotBeNull();
        chatUpdate.AdditionalProperties.Should().ContainKey("is_state_snapshot");
        ((bool)chatUpdate.AdditionalProperties!["is_state_snapshot"]!).Should().BeTrue();
    }

    [Fact]
    public async Task ComplexState_WithNestedObjectsAndArrays_RoundTripsCorrectlyAsync()
    {
        // Arrange
        var complexState = new
        {
            sessionId = "test-123",
            nested = new { value = "test", count = 10 },
            array = new[] { 1, 2, 3 },
            tags = new[] { "tag1", "tag2" }
        };
        var fakeAgent = new FakeStateAgent();

        await this.SetupTestServerAsync(fakeAgent);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread thread = (ChatClientAgentThread)agent.GetNewThread();

        string stateJson = JsonSerializer.Serialize(complexState);
        byte[] stateBytes = System.Text.Encoding.UTF8.GetBytes(stateJson);
        DataContent stateContent = new(stateBytes, "application/json");
        ChatMessage stateMessage = new(ChatRole.System, [stateContent]);
        ChatMessage userMessage = new(ChatRole.User, "process complex state");

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage, stateMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        AgentRunResponseUpdate? stateUpdate = updates.FirstOrDefault(u => u.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json"));
        stateUpdate.Should().NotBeNull();

        DataContent? dataContent = stateUpdate!.Contents.OfType<DataContent>().FirstOrDefault(dc => dc.MediaType == "application/json");
        string receivedJson = System.Text.Encoding.UTF8.GetString(dataContent!.Data.ToArray());
        JsonElement receivedState = JsonSerializer.Deserialize<JsonElement>(receivedJson);

        receivedState.GetProperty("sessionId").GetString().Should().Be("test-123");
        receivedState.GetProperty("nested").GetProperty("count").GetInt32().Should().Be(10);
        receivedState.GetProperty("array").GetArrayLength().Should().Be(3);
        receivedState.GetProperty("tags").GetArrayLength().Should().Be(2);
    }

    [Fact]
    public async Task StateSnapshot_CanBeUsedInSubsequentRequest_ForStateRoundTripAsync()
    {
        // Arrange
        var initialState = new { counter = 1, sessionId = "round-trip-test" };
        var fakeAgent = new FakeStateAgent();

        await this.SetupTestServerAsync(fakeAgent);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread thread = (ChatClientAgentThread)agent.GetNewThread();

        string stateJson = JsonSerializer.Serialize(initialState);
        byte[] stateBytes = System.Text.Encoding.UTF8.GetBytes(stateJson);
        DataContent stateContent = new(stateBytes, "application/json");
        ChatMessage stateMessage = new(ChatRole.System, [stateContent]);
        ChatMessage userMessage = new(ChatRole.User, "increment");

        List<AgentRunResponseUpdate> firstRoundUpdates = [];

        // Act - First round
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage, stateMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            firstRoundUpdates.Add(update);
        }

        // Extract state snapshot from first round
        AgentRunResponseUpdate? firstStateUpdate = firstRoundUpdates.FirstOrDefault(u => u.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json"));
        firstStateUpdate.Should().NotBeNull();
        DataContent? firstStateContent = firstStateUpdate!.Contents.OfType<DataContent>().FirstOrDefault(dc => dc.MediaType == "application/json");

        // Second round - use returned state
        ChatMessage secondStateMessage = new(ChatRole.System, [firstStateContent!]);
        ChatMessage secondUserMessage = new(ChatRole.User, "increment again");

        List<AgentRunResponseUpdate> secondRoundUpdates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([secondUserMessage, secondStateMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            secondRoundUpdates.Add(update);
        }

        // Assert - Second round should have incremented counter again
        AgentRunResponseUpdate? secondStateUpdate = secondRoundUpdates.FirstOrDefault(u => u.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json"));
        secondStateUpdate.Should().NotBeNull();

        DataContent? secondStateContent = secondStateUpdate!.Contents.OfType<DataContent>().FirstOrDefault(dc => dc.MediaType == "application/json");
        string secondStateJson = System.Text.Encoding.UTF8.GetString(secondStateContent!.Data.ToArray());
        JsonElement secondState = JsonSerializer.Deserialize<JsonElement>(secondStateJson);

        secondState.GetProperty("counter").GetInt32().Should().Be(3, "counter should be incremented twice: 1 -> 2 -> 3");
    }

    [Fact]
    public async Task WithoutState_AgentBehavesNormally_NoStateSnapshotReturnedAsync()
    {
        // Arrange
        var fakeAgent = new FakeStateAgent();

        await this.SetupTestServerAsync(fakeAgent);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread thread = (ChatClientAgentThread)agent.GetNewThread();

        ChatMessage userMessage = new(ChatRole.User, "hello");

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        updates.Should().NotBeEmpty();

        // Should NOT have state snapshot when no state is sent
        bool hasStateSnapshot = updates.Any(u => u.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json"));
        hasStateSnapshot.Should().BeFalse("should not return state snapshot when no state is provided");

        // Should have normal text response
        updates.Should().Contain(u => u.Contents.Any(c => c is TextContent));
    }

    [Fact]
    public async Task EmptyState_DoesNotTriggerStateHandlingAsync()
    {
        // Arrange
        var emptyState = new { };
        var fakeAgent = new FakeStateAgent();

        await this.SetupTestServerAsync(fakeAgent);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread thread = (ChatClientAgentThread)agent.GetNewThread();

        string stateJson = JsonSerializer.Serialize(emptyState);
        byte[] stateBytes = System.Text.Encoding.UTF8.GetBytes(stateJson);
        DataContent stateContent = new(stateBytes, "application/json");
        ChatMessage stateMessage = new(ChatRole.System, [stateContent]);
        ChatMessage userMessage = new(ChatRole.User, "hello");

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage, stateMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        updates.Should().NotBeEmpty();

        // Empty state {} should not trigger state snapshot mechanism
        bool hasEmptyStateSnapshot = updates.Any(u => u.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json"));
        hasEmptyStateSnapshot.Should().BeFalse("empty state should be treated as no state");

        // Should have normal response
        updates.Should().Contain(u => u.Contents.Any(c => c is TextContent));
    }

    [Fact]
    public async Task NonStreamingRunAsync_WithState_ReturnsStateInResponseAsync()
    {
        // Arrange
        var initialState = new { counter = 5 };
        var fakeAgent = new FakeStateAgent();

        await this.SetupTestServerAsync(fakeAgent);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread thread = (ChatClientAgentThread)agent.GetNewThread();

        string stateJson = JsonSerializer.Serialize(initialState);
        byte[] stateBytes = System.Text.Encoding.UTF8.GetBytes(stateJson);
        DataContent stateContent = new(stateBytes, "application/json");
        ChatMessage stateMessage = new(ChatRole.System, [stateContent]);
        ChatMessage userMessage = new(ChatRole.User, "process");

        // Act
        AgentRunResponse response = await agent.RunAsync([userMessage, stateMessage], thread, new AgentRunOptions(), CancellationToken.None);

        // Assert
        response.Should().NotBeNull();
        response.Messages.Should().NotBeEmpty();

        // Should have message with DataContent containing state
        bool hasStateMessage = response.Messages.Any(m => m.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json"));
        hasStateMessage.Should().BeTrue("response should contain state message");

        ChatMessage? stateResponseMessage = response.Messages.FirstOrDefault(m => m.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json"));
        stateResponseMessage.Should().NotBeNull();

        DataContent? dataContent = stateResponseMessage!.Contents.OfType<DataContent>().FirstOrDefault(dc => dc.MediaType == "application/json");
        string receivedJson = System.Text.Encoding.UTF8.GetString(dataContent!.Data.ToArray());
        JsonElement receivedState = JsonSerializer.Deserialize<JsonElement>(receivedJson);
        receivedState.GetProperty("counter").GetInt32().Should().Be(6);
    }

    private async Task SetupTestServerAsync(FakeStateAgent fakeAgent)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Services.AddAGUI();
        builder.WebHost.UseTestServer();

        this._app = builder.Build();

        this._app.MapAGUI("/agent", fakeAgent);

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

    public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        return this.RunStreamingAsync(messages, thread, options, cancellationToken).ToAgentRunResponseAsync(cancellationToken);
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Check for state in ChatOptions.AdditionalProperties (set by AG-UI hosting layer)
        if (options is ChatClientAgentRunOptions { ChatOptions.AdditionalProperties: { } properties } &&
            properties.TryGetValue("ag_ui_state", out object? stateObj) &&
            stateObj is JsonElement state &&
            state.ValueKind == JsonValueKind.Object)
        {
            // Check if state object has properties (not empty {})
            bool hasProperties = false;
            foreach (JsonProperty _ in state.EnumerateObject())
            {
                hasProperties = true;
                break;
            }

            if (hasProperties)
            {
                // State is present and non-empty - modify it and return as DataContent
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
                    else if (prop.Value.ValueKind == JsonValueKind.Object || prop.Value.ValueKind == JsonValueKind.Array)
                    {
                        modifiedState[prop.Name] = prop.Value;
                    }
                }

                // Return modified state as DataContent
                string modifiedStateJson = JsonSerializer.Serialize(modifiedState);
                byte[] modifiedStateBytes = System.Text.Encoding.UTF8.GetBytes(modifiedStateJson);
                DataContent modifiedStateContent = new(modifiedStateBytes, "application/json");

                yield return new AgentRunResponseUpdate
                {
                    MessageId = Guid.NewGuid().ToString("N"),
                    Role = ChatRole.Assistant,
                    Contents = [modifiedStateContent]
                };
            }
        }

        // Always return a text response
        string messageId = Guid.NewGuid().ToString("N");
        yield return new AgentRunResponseUpdate
        {
            MessageId = messageId,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("State processed")]
        };

        await Task.CompletedTask;
    }

    public override AgentThread GetNewThread() => new FakeInMemoryAgentThread();

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return new FakeInMemoryAgentThread(serializedThread, jsonSerializerOptions);
    }

    private sealed class FakeInMemoryAgentThread : InMemoryAgentThread
    {
        public FakeInMemoryAgentThread()
            : base()
        {
        }

        public FakeInMemoryAgentThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            : base(serializedThread, jsonSerializerOptions)
        {
        }
    }

    public override object? GetService(Type serviceType, object? serviceKey = null) => null;
}
