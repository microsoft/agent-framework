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
        AGUIAgent agent = new("assistant", "Sample assistant", [], this._client!, "");
        AgentThread thread = agent.GetNewThread();
        ChatMessage userMessage = new(ChatRole.User, "hello");

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        InMemoryAgentThread? inMemoryThread = thread.GetService<InMemoryAgentThread>();
        inMemoryThread.Should().NotBeNull();
        inMemoryThread!.MessageStore.Should().HaveCount(2);
        inMemoryThread.MessageStore[0].Role.Should().Be(ChatRole.User);
        inMemoryThread.MessageStore[0].Text.Should().Be("hello");
        inMemoryThread.MessageStore[1].Role.Should().Be(ChatRole.Assistant);
        inMemoryThread.MessageStore[1].Text.Should().Be("Hello from fake agent!");

        updates.Should().NotBeEmpty();
        updates.Should().AllSatisfy(u => u.Role.Should().Be(ChatRole.Assistant));
    }

    [Fact]
    public async Task ClientReceivesRunLifecycleEventsAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        AGUIAgent agent = new("assistant", "Sample assistant", [], this._client!, "");
        AgentThread thread = agent.GetNewThread();
        ChatMessage userMessage = new(ChatRole.User, "test");

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - RunStarted should be the first update
        updates.Should().NotBeEmpty();
        updates[0].Contents.Should().ContainSingle();
        RunStartedContent runStarted = updates[0].Contents[0].Should().BeOfType<RunStartedContent>().Subject;
        runStarted.ThreadId.Should().NotBeNullOrEmpty();
        runStarted.RunId.Should().NotBeNullOrEmpty();

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
        lastUpdate.Contents.Should().ContainSingle();
        RunFinishedContent runFinished = lastUpdate.Contents[0].Should().BeOfType<RunFinishedContent>().Subject;
        runFinished.ThreadId.Should().Be(runStarted.ThreadId);
        runFinished.RunId.Should().Be(runStarted.RunId);
    }

    [Fact]
    public async Task RunAsyncAggregatesStreamingUpdatesAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        AGUIAgent agent = new("assistant", "Sample assistant", [], this._client!, "");
        AgentThread thread = agent.GetNewThread();
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
        AGUIAgent agent = new("assistant", "Sample assistant", [], this._client!, "");
        AgentThread thread = agent.GetNewThread();
        ChatMessage firstUserMessage = new(ChatRole.User, "First question");

        // Act - First turn
        List<AgentRunResponseUpdate> firstTurnUpdates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([firstUserMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            firstTurnUpdates.Add(update);
        }

        // Assert first turn completed
        firstTurnUpdates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));

        // Act - Second turn with another message
        ChatMessage secondUserMessage = new(ChatRole.User, "Second question");
        List<AgentRunResponseUpdate> secondTurnUpdates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([secondUserMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            secondTurnUpdates.Add(update);
        }

        // Assert second turn completed
        secondTurnUpdates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));

        // Assert - Thread should contain all 4 messages (2 user + 2 assistant)
        InMemoryAgentThread? inMemoryThread = thread.GetService<InMemoryAgentThread>();
        inMemoryThread.Should().NotBeNull();
        inMemoryThread!.MessageStore.Should().HaveCount(4);

        // Verify message order and content
        inMemoryThread.MessageStore[0].Role.Should().Be(ChatRole.User);
        inMemoryThread.MessageStore[0].Text.Should().Be("First question");

        inMemoryThread.MessageStore[1].Role.Should().Be(ChatRole.Assistant);
        inMemoryThread.MessageStore[1].Text.Should().Be("Hello from fake agent!");

        inMemoryThread.MessageStore[2].Role.Should().Be(ChatRole.User);
        inMemoryThread.MessageStore[2].Text.Should().Be("Second question");

        inMemoryThread.MessageStore[3].Role.Should().Be(ChatRole.Assistant);
        inMemoryThread.MessageStore[3].Text.Should().Be("Hello from fake agent!");
    }

    [Fact]
    public async Task AgentSendsMultipleMessagesInOneTurnAsync()
    {
        // Arrange
        await this.SetupTestServerAsync(useMultiMessageAgent: true);
        AGUIAgent agent = new("assistant", "Sample assistant", [], this._client!, "");
        AgentThread thread = agent.GetNewThread();
        ChatMessage userMessage = new(ChatRole.User, "Tell me a story");

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage], thread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - Should have received text updates with different message IDs
        List<AgentRunResponseUpdate> textUpdates = updates.Where(u => !string.IsNullOrEmpty(u.Text)).ToList();
        textUpdates.Should().NotBeEmpty();

        // Extract unique message IDs
        List<string> messageIds = textUpdates.Select(u => u.MessageId).Where(id => !string.IsNullOrEmpty(id)).Distinct().ToList()!;
        messageIds.Should().HaveCountGreaterThan(1, "agent should send multiple messages");

        // Verify thread contains user message plus multiple assistant messages
        InMemoryAgentThread? inMemoryThread = thread.GetService<InMemoryAgentThread>();
        inMemoryThread.Should().NotBeNull();
        inMemoryThread!.MessageStore.Should().HaveCountGreaterThan(2);
        inMemoryThread.MessageStore[0].Role.Should().Be(ChatRole.User);
        inMemoryThread.MessageStore.Skip(1).Should().AllSatisfy(m => m.Role.Should().Be(ChatRole.Assistant));
    }

    [Fact]
    public async Task UserSendsMultipleMessagesAtOnceAsync()
    {
        // Arrange
        await this.SetupTestServerAsync();
        AGUIAgent agent = new("assistant", "Sample assistant", [], this._client!, "");
        AgentThread thread = agent.GetNewThread();

        // Multiple user messages sent in one turn
        ChatMessage[] userMessages =
        [
            new ChatMessage(ChatRole.User, "First part of question"),
            new ChatMessage(ChatRole.User, "Second part of question"),
            new ChatMessage(ChatRole.User, "Third part of question")
        ];

        List<AgentRunResponseUpdate> updates = [];

        // Act
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(userMessages, thread, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert - Should have received assistant response
        updates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));

        // Verify thread contains all user messages plus assistant response
        InMemoryAgentThread? inMemoryThread = thread.GetService<InMemoryAgentThread>();
        inMemoryThread.Should().NotBeNull();
        inMemoryThread!.MessageStore.Should().HaveCount(4); // 3 user + 1 assistant

        inMemoryThread.MessageStore[0].Role.Should().Be(ChatRole.User);
        inMemoryThread.MessageStore[0].Text.Should().Be("First part of question");

        inMemoryThread.MessageStore[1].Role.Should().Be(ChatRole.User);
        inMemoryThread.MessageStore[1].Text.Should().Be("Second part of question");

        inMemoryThread.MessageStore[2].Role.Should().Be(ChatRole.User);
        inMemoryThread.MessageStore[2].Text.Should().Be("Third part of question");

        inMemoryThread.MessageStore[3].Role.Should().Be(ChatRole.Assistant);
        inMemoryThread.MessageStore[3].Text.Should().Be("Hello from fake agent!");
    }

    private async Task SetupTestServerAsync(bool useMultiMessageAgent = false)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        if (useMultiMessageAgent)
        {
            builder.Services.AddSingleton<FakeMultiMessageAgent>();
        }
        else
        {
            builder.Services.AddSingleton<FakeChatClientAgent>();
        }

        this._app = builder.Build();

        if (useMultiMessageAgent)
        {
            this._app.MapAGUIAgent("/agent", (IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, IEnumerable<KeyValuePair<string, string>> context, JsonElement forwardedProps) =>
                this._app.Services.GetRequiredService<FakeMultiMessageAgent>());
        }
        else
        {
            this._app.MapAGUIAgent("/agent", (IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, IEnumerable<KeyValuePair<string, string>> context, JsonElement forwardedProps) =>
                this._app.Services.GetRequiredService<FakeChatClientAgent>());
        }

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
}
