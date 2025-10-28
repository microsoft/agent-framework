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
using Xunit;

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

        // Assert - Should have received text updates
        updates.Should().Contain(u => !string.IsNullOrEmpty(u.Text));

        // All updates should have the same message ID
        string? firstMessageId = updates.FirstOrDefault()?.MessageId;
        firstMessageId.Should().NotBeNullOrEmpty();
        updates.Should().AllSatisfy(u => u.MessageId.Should().Be(firstMessageId));
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

    private async Task SetupTestServerAsync()
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        builder.Services.AddSingleton<FakeChatClientAgent>();

        this._app = builder.Build();

        this._app.MapAGUIAgent("/agent", (IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, IEnumerable<KeyValuePair<string, string>> context, JsonElement forwardedProps) =>
            this._app.Services.GetRequiredService<FakeChatClientAgent>());

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
        List<ChatMessage> chatMessages = [];
        await foreach (AgentRunResponseUpdate update in this.RunStreamingAsync(messages, thread, options, cancellationToken).ConfigureAwait(false))
        {
            if (update.Role.HasValue && update.Contents.Count > 0)
            {
                chatMessages.Add(new ChatMessage(update.Role.Value, update.Contents));
            }
        }

        return new AgentRunResponse(chatMessages);
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

            await Task.Delay(10, cancellationToken).ConfigureAwait(false);
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
