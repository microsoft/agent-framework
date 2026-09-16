// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the in-box session stores.
/// </summary>
public class InMemoryAgentSessionStoreTests
{
    [Fact]
    public async Task GetSessionAsync_MissingSession_ReturnsNullAsync()
    {
        // Arrange
        var store = new InMemoryAgentSessionStore();
        var agent = new Mock<AIAgent>();

        // Act
        AgentSession? session = await store.GetSessionAsync(agent.Object, new AgentSessionStoreKey("missing"));

        // Assert
        Assert.Null(session);
    }

    [Fact]
    public async Task GetSessionAsync_ReturnsIndependentSnapshot_ForConcurrentBranchesAsync()
    {
        // Arrange: a real agent so the store round-trips the session through genuine serialize/deserialize,
        // and a stored session that carries some state to copy.
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        var store = new InMemoryAgentSessionStore();
        var key = new AgentSessionStoreKey("s1").WithPartition("user", "user-1");

        AgentSession original = await agent.CreateSessionAsync();
        original.StateBag.SetValue("marker", "v1");
        await store.SaveSessionAsync(agent, key, original);

        // Act: two concurrent branches read the same stored id.
        AgentSession? branchA = await store.GetSessionAsync(agent, key);
        AgentSession? branchB = await store.GetSessionAsync(agent, key);

        // Assert: each branch is an independent instance carrying the same content.
        Assert.NotNull(branchA);
        Assert.NotNull(branchB);
        Assert.NotSame(branchA, branchB);
        Assert.Equal("v1", branchA.StateBag.GetValue<string>("marker"));
        Assert.Equal("v1", branchB.StateBag.GetValue<string>("marker"));

        // Mutating one branch must not affect the other branch or the stored snapshot.
        branchA.StateBag.SetValue("marker", "mutated");
        Assert.Equal("v1", branchB.StateBag.GetValue<string>("marker"));

        AgentSession? branchC = await store.GetSessionAsync(agent, key);
        Assert.NotNull(branchC);
        Assert.Equal("v1", branchC.StateBag.GetValue<string>("marker"));
    }

    [Fact]
    public async Task GetSessionAsync_DifferentUsers_AreIsolatedAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        var store = new InMemoryAgentSessionStore();
        var user1Key = new AgentSessionStoreKey("s1").WithPartition("user", "user-1");
        var user2Key = new AgentSessionStoreKey("s1").WithPartition("user", "user-2");
        AgentSession session = await agent.CreateSessionAsync();
        session.StateBag.SetValue("marker", "user-1");
        await store.SaveSessionAsync(agent, user1Key, session);

        // Act
        AgentSession? matchingUser = await store.GetSessionAsync(agent, user1Key);
        AgentSession? differentUser = await store.GetSessionAsync(agent, user2Key);

        // Assert
        Assert.NotNull(matchingUser);
        Assert.Equal("user-1", matchingUser.StateBag.GetValue<string>("marker"));
        Assert.Null(differentUser);
    }

    [Fact]
    public async Task SaveSessionAsync_OriginalMutationAndOverwrite_PreserveSnapshotsAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient());
        var store = new InMemoryAgentSessionStore();
        var key = new AgentSessionStoreKey("session");
        AgentSession session = await agent.CreateSessionAsync();
        session.StateBag.SetValue("marker", "first");
        await store.SaveSessionAsync(agent, key, session);

        // Act
        session.StateBag.SetValue("marker", "second");
        AgentSession? first = await store.GetSessionAsync(agent, key);
        await store.SaveSessionAsync(agent, key, session);
        AgentSession? second = await store.GetSessionAsync(agent, key);

        // Assert
        Assert.Equal("first", first!.StateBag.GetValue<string>("marker"));
        Assert.Equal("second", second!.StateBag.GetValue<string>("marker"));
    }

    [Fact]
    public async Task GetSessionAsync_SameNameDifferentAgentIds_AreIsolatedAsync()
    {
        // Arrange
        AIAgent first = new ChatClientAgent(new NotInvokedChatClient(), name: "same-name");
        AIAgent second = new ChatClientAgent(new NotInvokedChatClient(), name: "same-name");
        var store = new InMemoryAgentSessionStore();
        var key = new AgentSessionStoreKey("session");
        await store.SaveSessionAsync(first, key, await first.CreateSessionAsync());

        // Act
        AgentSession? result = await store.GetSessionAsync(second, key);

        // Assert
        Assert.NotEqual(first.Id, second.Id);
        Assert.Null(result);
    }

    [Fact]
    public async Task GetSessionAsync_CompositePartitions_PreserveAllKeyBoundariesAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient());
        var store = new InMemoryAgentSessionStore();
        var key = new AgentSessionStoreKey("session").WithPartition("user", "alice").WithPartition("tenant", "one");
        await store.SaveSessionAsync(agent, key, await agent.CreateSessionAsync());
        var reordered = new AgentSessionStoreKey("session").WithPartition("tenant", "one").WithPartition("user", "alice");

        // Act and assert
        Assert.NotNull(await store.GetSessionAsync(agent, reordered));
        Assert.Null(await store.GetSessionAsync(agent, key.WithPartition("tenant", "two")));
        Assert.Null(await store.GetSessionAsync(agent, key.WithPartition("user", "Alice")));
        Assert.Null(await store.GetSessionAsync(agent, new AgentSessionStoreKey("session").WithPartition("user", "alice")));
        Assert.Null(await store.GetSessionAsync(agent, new AgentSessionStoreKey("other", key.Partitions)));
        Assert.Null(await store.GetSessionAsync(agent, new AgentSessionStoreKey("session")));
    }

    [Fact]
    public async Task SaveAndGetSessionAsync_NullArguments_ThrowAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient());
        var store = new InMemoryAgentSessionStore();
        var key = new AgentSessionStoreKey("session");
        AgentSession session = await agent.CreateSessionAsync();

        // Act and assert
        await Assert.ThrowsAsync<ArgumentNullException>("agent", async () => await store.SaveSessionAsync(null!, key, session));
        await Assert.ThrowsAsync<ArgumentNullException>("key", async () => await store.SaveSessionAsync(agent, null!, session));
        await Assert.ThrowsAsync<ArgumentNullException>("session", async () => await store.SaveSessionAsync(agent, key, null!));
        await Assert.ThrowsAsync<ArgumentNullException>("agent", async () => await store.GetSessionAsync(null!, key));
        await Assert.ThrowsAsync<ArgumentNullException>("key", async () => await store.GetSessionAsync(agent, null!));
    }

    [Fact]
    public async Task SaveSessionAsync_FailedSerialization_PreservesPreviousSnapshotAndForwardsCancellationAsync()
    {
        // Arrange
        var agent = new TrackingAgent(new ChatClientAgent(new NotInvokedChatClient()));
        var store = new InMemoryAgentSessionStore();
        var key = new AgentSessionStoreKey("session");
        using var cancellation = new CancellationTokenSource();
        AgentSession original = await agent.CreateSessionAsync();
        original.StateBag.SetValue("marker", "saved");
        await store.SaveSessionAsync(agent, key, original, cancellation.Token);
        Assert.Equal(cancellation.Token, agent.SerializeToken);
        original.StateBag.SetValue("marker", "failed");
        agent.FailSerialization = true;

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await store.SaveSessionAsync(agent, key, original, cancellation.Token));
        AgentSession? restored = await store.GetSessionAsync(agent, key, cancellation.Token);

        // Assert
        Assert.NotNull(restored);
        Assert.Equal("saved", restored.StateBag.GetValue<string>("marker"));
        Assert.Equal(cancellation.Token, agent.DeserializeToken);
    }

    private sealed class TrackingAgent(AIAgent innerAgent) : DelegatingAIAgent(innerAgent)
    {
        public bool FailSerialization { get; set; }
        public CancellationToken SerializeToken { get; private set; }
        public CancellationToken DeserializeToken { get; private set; }

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            this.SerializeToken = cancellationToken;
            if (this.FailSerialization)
            {
                throw new InvalidOperationException("Cannot serialize session.");
            }

            return base.SerializeSessionCoreAsync(session, jsonSerializerOptions, cancellationToken);
        }

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            this.DeserializeToken = cancellationToken;
            return base.DeserializeSessionCoreAsync(serializedState, jsonSerializerOptions, cancellationToken);
        }
    }

    // A chat client that is never invoked: these tests only create, serialize, and deserialize sessions.
    private sealed class NotInvokedChatClient : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose()
        {
        }
    }
}
