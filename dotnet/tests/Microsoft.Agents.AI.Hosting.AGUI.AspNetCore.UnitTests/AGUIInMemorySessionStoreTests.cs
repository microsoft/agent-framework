// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Unit tests for <see cref="AGUIInMemorySessionStore"/>.
/// </summary>
public sealed class AGUIInMemorySessionStoreTests
{
    [Fact]
    public async Task GetOrCreateSessionAsync_ReusesSessionForSameThreadAsync()
    {
        // Arrange
        var store = new AGUIInMemorySessionStore();
        var agent = new CountingAgent();

        // Act
        AgentSession firstSession = await store.GetOrCreateSessionAsync(agent, "thread-1");
        AgentSession secondSession = await store.GetOrCreateSessionAsync(agent, "thread-1");
        AgentSession thirdSession = await store.GetOrCreateSessionAsync(agent, "thread-2");

        // Assert
        Assert.Same(firstSession, secondSession);
        Assert.NotSame(firstSession, thirdSession);
        Assert.Equal(2, agent.CreateSessionCallCount);
    }

    [Fact]
    public async Task GetOrCreateSessionAsync_UsesAgentIdentityInCacheKeyAsync()
    {
        // Arrange
        var store = new AGUIInMemorySessionStore();
        var firstAgent = new CountingAgent("agent-1");
        var secondAgent = new CountingAgent("agent-2");

        // Act
        AgentSession firstSession = await store.GetOrCreateSessionAsync(firstAgent, "shared-thread");
        AgentSession secondSession = await store.GetOrCreateSessionAsync(secondAgent, "shared-thread");

        // Assert
        Assert.NotSame(firstSession, secondSession);
        Assert.Equal(1, firstAgent.CreateSessionCallCount);
        Assert.Equal(1, secondAgent.CreateSessionCallCount);
    }

    [Fact]
    public async Task GetOrCreateSessionAsync_DoesNotCollideWhenKeyPartsContainColonAsync()
    {
        // Arrange
        var store = new AGUIInMemorySessionStore();
        var firstAgent = new CountingAgent("a:b");
        var secondAgent = new CountingAgent("a");

        // Act
        AgentSession firstSession = await store.GetOrCreateSessionAsync(firstAgent, "c");
        AgentSession secondSession = await store.GetOrCreateSessionAsync(secondAgent, "b:c");

        // Assert
        Assert.NotSame(firstSession, secondSession);
        Assert.Equal(1, firstAgent.CreateSessionCallCount);
        Assert.Equal(1, secondAgent.CreateSessionCallCount);
    }

    [Fact]
    public async Task GetOrCreateSessionAsync_RecreatesExpiredSessionAsync()
    {
        // Arrange
        var store = new AGUIInMemorySessionStore(new AGUIInMemorySessionStoreOptions
        {
            SlidingExpiration = TimeSpan.FromMilliseconds(20)
        });
        var agent = new CountingAgent();

        // Act
        AgentSession firstSession = await store.GetOrCreateSessionAsync(agent, "thread-1");
        await Task.Delay(TimeSpan.FromMilliseconds(80));
        AgentSession secondSession = await store.GetOrCreateSessionAsync(agent, "thread-1");

        // Assert
        Assert.NotSame(firstSession, secondSession);
        Assert.Equal(2, agent.CreateSessionCallCount);
    }

    [Fact]
    public async Task GetOrCreateSessionAsync_CreatesSingleSessionUnderConcurrencyAsync()
    {
        // Arrange
        var store = new AGUIInMemorySessionStore();
        var agent = new BlockingAgent();

        // Act
        Task<AgentSession> firstTask = store.GetOrCreateSessionAsync(agent, "thread-1").AsTask();
        await agent.SessionCreationStarted.Task;

        Task<AgentSession> secondTask = store.GetOrCreateSessionAsync(agent, "thread-1").AsTask();
        Task<AgentSession> thirdTask = store.GetOrCreateSessionAsync(agent, "thread-1").AsTask();

        agent.AllowSessionCreation.TrySetResult();
        AgentSession[] sessions = await Task.WhenAll(firstTask, secondTask, thirdTask);

        // Assert
        Assert.Equal(1, agent.CreateSessionCallCount);
        Assert.Same(sessions[0], sessions[1]);
        Assert.Same(sessions[1], sessions[2]);
    }

    private sealed class CountingAgent : AIAgent
    {
        private readonly string _id;

        public CountingAgent(string id = "counting-agent")
        {
            this._id = id;
        }

        public int CreateSessionCallCount { get; private set; }

        protected override string? IdCore => this._id;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        {
            this.CreateSessionCallCount++;
            return new(new CountingSession());
        }

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<Microsoft.Extensions.AI.ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<Microsoft.Extensions.AI.ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        private sealed class CountingSession : AgentSession
        {
        }
    }

    private sealed class BlockingAgent : AIAgent
    {
        public TaskCompletionSource SessionCreationStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TaskCompletionSource AllowSessionCreation { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public int CreateSessionCallCount { get; private set; }

        protected override string? IdCore => "blocking-agent";

        protected override async ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        {
            this.CreateSessionCallCount++;
            this.SessionCreationStarted.TrySetResult();
            await this.AllowSessionCreation.Task.ConfigureAwait(false);
            return new BlockingSession();
        }

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<Microsoft.Extensions.AI.ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<Microsoft.Extensions.AI.ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        private sealed class BlockingSession : AgentSession
        {
        }
    }
}