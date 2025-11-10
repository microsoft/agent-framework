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

public sealed class BasicStreamingTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _client;

    [Fact]
    public async Task ClientReceivesStreamedAssistantMessageAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
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
        thread.Should().NotBeNull();

        updates.Should().NotBeEmpty();
        updates.Should().AllSatisfy(u => u.Role.Should().Be(ChatRole.Assistant));

        // Verify assistant response message
        AgentRunResponse response = updates.ToAgentRunResponse();
        response.Messages.Should().HaveCount(1);
        response.Messages[0].Role.Should().Be(ChatRole.Assistant);
        response.Messages[0].Text.Should().Be("Hello from fake agent!");
    }

    [Fact]
    public async Task ClientReceivesRunLifecycleEventsAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread thread = (ChatClientAgentThread)agent.GetNewThread();
        ChatMessage userMessage = new(ChatRole.User, "test");

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - RunStarted should be the first update
        updates.Should().NotBeEmpty();
        updates[0].ResponseId.Should().NotBeNullOrEmpty();
        ChatResponseUpdate firstUpdate = updates[0].AsChatResponseUpdate();
        string? threadId = firstUpdate.ConversationId;
        string? runId = updates[0].ResponseId;
        threadId.Should().NotBeNullOrEmpty();
        runId.Should().NotBeNullOrEmpty();

        // Should have received text updates
        updates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));

        // All text content updates should have the same message ID
        List<AgentRunResponseUpdate> textUpdates = updates.Where(u => !string.IsNullOrEmpty(u.Text)).ToList();
        textUpdates.Should().NotBeEmpty();
        string? firstMessageId = textUpdates.FirstOrDefault()?.MessageId;
        firstMessageId.Should().NotBeNullOrEmpty();
        textUpdates.Should().AllSatisfy(u => u.MessageId.Should().Be(firstMessageId));

        // RunFinished should be the last update
        AgentRunResponseUpdate lastUpdate = updates[^1];
        lastUpdate.ResponseId.Should().Be(runId);
        ChatResponseUpdate lastChatUpdate = lastUpdate.AsChatResponseUpdate();
        lastChatUpdate.ConversationId.Should().Be(threadId);
    }

    [Fact]
    public async Task RunAsyncAggregatesStreamingUpdatesAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread thread = (ChatClientAgentThread)agent.GetNewThread();
        ChatMessage userMessage = new(ChatRole.User, "hello");

        // Act
        AgentRunResponse response = await agent.RunAsync([userMessage], thread, new AgentRunOptions(), CancellationToken.None);

        // Assert
        response.Messages.Should().NotBeEmpty();
        response.Messages.Should().Contain(m => m.Role == ChatRole.Assistant);
        response.Messages.Should().Contain(m => m.Text == "Hello from fake agent!");
    }

    [Fact]
    public async Task MultiTurnConversationPreservesAllMessagesInThreadAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread chatClientThread = (ChatClientAgentThread)agent.GetNewThread();
        ChatMessage firstUserMessage = new(ChatRole.User, "First question");

        // Act - First turn
        List<AgentRunResponseUpdate> firstTurnUpdates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([firstUserMessage], chatClientThread, new AgentRunOptions(), CancellationToken.None))
        {
            firstTurnUpdates.Add(update);
        }

        // Assert first turn completed
        firstTurnUpdates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));

        // Act - Second turn with another message
        ChatMessage secondUserMessage = new(ChatRole.User, "Second question");
        List<AgentRunResponseUpdate> secondTurnUpdates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([secondUserMessage], chatClientThread, new AgentRunOptions(), CancellationToken.None))
        {
            secondTurnUpdates.Add(update);
        }

        // Assert second turn completed
        secondTurnUpdates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));

        // Verify first turn assistant response
        AgentRunResponse firstResponse = firstTurnUpdates.ToAgentRunResponse();
        firstResponse.Messages.Should().HaveCount(1);
        firstResponse.Messages[0].Role.Should().Be(ChatRole.Assistant);
        firstResponse.Messages[0].Text.Should().Be("Hello from fake agent!");

        // Verify second turn assistant response
        AgentRunResponse secondResponse = secondTurnUpdates.ToAgentRunResponse();
        secondResponse.Messages.Should().HaveCount(1);
        secondResponse.Messages[0].Role.Should().Be(ChatRole.Assistant);
        secondResponse.Messages[0].Text.Should().Be("Hello from fake agent!");
    }

    [Fact]
    public async Task AgentSendsMultipleMessagesInOneTurnAsync()
    {
        // Arrange
        await this.SetupTestServerAsync(useMultiMessageAgent: true);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread chatClientThread = (ChatClientAgentThread)agent.GetNewThread();
        ChatMessage userMessage = new(ChatRole.User, "Tell me a story");

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage], chatClientThread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - Should have received text updates with different message IDs
        List<AgentRunResponseUpdate> textUpdates = updates.Where(u => !string.IsNullOrEmpty(u.Text)).ToList();
        textUpdates.Should().NotBeEmpty();

        // Extract unique message IDs
        List<string> messageIds = textUpdates.Select(u => u.MessageId).Where(id => !string.IsNullOrEmpty(id)).Distinct().ToList()!;
        messageIds.Should().HaveCountGreaterThan(1, "agent should send multiple messages");

        // Verify assistant messages from updates
        AgentRunResponse response = updates.ToAgentRunResponse();
        response.Messages.Should().HaveCountGreaterThan(1);
        response.Messages.Should().AllSatisfy(m => m.Role.Should().Be(ChatRole.Assistant));
    }

    [Fact]
    public async Task UserSendsMultipleMessagesAtOnceAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        ChatClientAgentThread chatClientThread = (ChatClientAgentThread)agent.GetNewThread();

        // Multiple user messages sent in one turn
        ChatMessage[] userMessages =
        [
            new ChatMessage(ChatRole.User, "First part of question"),
            new ChatMessage(ChatRole.User, "Second part of question"),
            new ChatMessage(ChatRole.User, "Third part of question")
        ];

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(userMessages, chatClientThread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - Should have received assistant response
        updates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));
        updates.Should().Contain(u => u.Role == ChatRole.Assistant);

        // Verify assistant response message
        AgentRunResponse response = updates.ToAgentRunResponse();
        response.Messages.Should().HaveCount(1);
        response.Messages[0].Role.Should().Be(ChatRole.Assistant);
        response.Messages[0].Text.Should().Be("Hello from fake agent!");
    }

    private async Task SetupTestServerAsync(bool useMultiMessageAgent = false)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        builder.Services.AddAGUI();

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

        this._app.MapAGUI("/agent", agent);

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
    private readonly string _agentId;
    private readonly string _description;

    public FakeChatClientAgent()
    {
        this._agentId = "fake-agent";
        this._description = "A fake agent for testing";
    }

    public override string Id => this._agentId;

    public override string? Description => this._description;

    public override AgentThread GetNewThread()
    {
        return new FakeInMemoryAgentThread();
    }

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return new FakeInMemoryAgentThread(serializedThread, jsonSerializerOptions);
    }

    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in this.RunStreamingAsync(messages, thread, options, cancellationToken).ConfigureAwait(false))
        {
            updates.Add(update);
        }

        return updates.ToAgentRunResponse();
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string messageId = Guid.NewGuid().ToString("N");

        // Simulate streaming a deterministic response
        foreach (string chunk in new[] { "Hello", " ", "from", " ", "fake", " ", "agent", "!" })
        {
            yield return new AgentRunResponseUpdate
            {
                MessageId = messageId,
                Role = ChatRole.Assistant,
                Contents = [new TextContent(chunk)]
            };

            await Task.Yield();
        }
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
}

[SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated via dependency injection")]
internal sealed class FakeMultiMessageAgent : AIAgent
{
    private readonly string _agentId;
    private readonly string _description;

    public FakeMultiMessageAgent()
    {
        this._agentId = "fake-multi-message-agent";
        this._description = "A fake agent that sends multiple messages for testing";
    }

    public override string Id => this._agentId;

    public override string? Description => this._description;

    public override AgentThread GetNewThread()
    {
        return new FakeInMemoryAgentThread();
    }

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return new FakeInMemoryAgentThread(serializedThread, jsonSerializerOptions);
    }

    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in this.RunStreamingAsync(messages, thread, options, cancellationToken).ConfigureAwait(false))
        {
            updates.Add(update);
        }

        return updates.ToAgentRunResponse();
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Simulate sending first message
        string messageId1 = Guid.NewGuid().ToString("N");
        foreach (string chunk in new[] { "First", " ", "message" })
        {
            yield return new AgentRunResponseUpdate
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
            yield return new AgentRunResponseUpdate
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
            yield return new AgentRunResponseUpdate
            {
                MessageId = messageId3,
                Role = ChatRole.Assistant,
                Contents = [new TextContent(chunk)]
            };

            await Task.Yield();
        }
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
