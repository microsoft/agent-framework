// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

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
