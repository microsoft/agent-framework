// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentSessionStore.DeleteSessionAsync"/> across the in-box stores.
/// </summary>
public class InMemoryAgentSessionStoreTests
{
    [Fact]
    public async Task DeleteSessionAsync_RemovesStoredSession_SoNextGetCreatesAsync()
    {
        // Arrange
        var stored = JsonSerializer.SerializeToElement(new { marker = "stored" });
        var restoredSession = new TestAgentSession();
        var createdSession = new TestAgentSession();
        var agent = new Mock<AIAgent>();
        agent.Protected()
            .Setup<ValueTask<JsonElement>>("SerializeSessionCoreAsync", ItExpr.IsAny<AgentSession>(), ItExpr.IsAny<JsonSerializerOptions>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask<JsonElement>(stored));
        agent.Protected()
            .Setup<ValueTask<AgentSession>>("DeserializeSessionCoreAsync", ItExpr.IsAny<JsonElement>(), ItExpr.IsAny<JsonSerializerOptions>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask<AgentSession>(restoredSession));
        agent.Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask<AgentSession>(createdSession));

        var store = new InMemoryAgentSessionStore();

        // Act & Assert
        await store.SaveSessionAsync(agent.Object, "s1", new TestAgentSession());
        Assert.Same(restoredSession, await store.GetSessionAsync(agent.Object, "s1"));

        await store.DeleteSessionAsync(agent.Object, "s1");
        Assert.Same(createdSession, await store.GetSessionAsync(agent.Object, "s1"));
    }

    [Fact]
    public async Task DeleteSessionAsync_UnknownId_DoesNotThrowAsync()
    {
        // Arrange
        var store = new InMemoryAgentSessionStore();

        // Act & Assert (no exception)
        await store.DeleteSessionAsync(new Mock<AIAgent>().Object, "missing");
    }

    [Fact]
    public async Task DeleteSessionAsync_NoopStore_CompletesAsync()
    {
        // Arrange
        var store = new NoopAgentSessionStore();

        // Act & Assert (no exception)
        await store.DeleteSessionAsync(new Mock<AIAgent>().Object, "any");
    }

    [Fact]
    public async Task DeleteSessionAsync_StoreOptsOut_ThrowsNotSupportedAsync()
    {
        // Arrange: a store that chooses not to support deletion throws NotSupportedException itself.
        AgentSessionStore store = new ConcreteAgentSessionStore();

        // Act & Assert
        await Assert.ThrowsAsync<NotSupportedException>(() => store.DeleteSessionAsync(new Mock<AIAgent>().Object, "any").AsTask());
    }

    [Fact]
    public async Task GetSessionAsync_ReturnsIndependentSnapshot_ForConcurrentBranchesAsync()
    {
        // Arrange: a real agent so the store round-trips the session through genuine serialize/deserialize,
        // and a stored session that carries some state to copy.
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        var store = new InMemoryAgentSessionStore();

        AgentSession original = await agent.CreateSessionAsync();
        original.StateBag.SetValue("marker", "v1");
        await store.SaveSessionAsync(agent, "s1", original);

        // Act: two concurrent branches read the same stored id.
        AgentSession branchA = await store.GetSessionAsync(agent, "s1");
        AgentSession branchB = await store.GetSessionAsync(agent, "s1");

        // Assert: each branch is an independent instance carrying the same content.
        Assert.NotSame(branchA, branchB);
        Assert.Equal("v1", branchA.StateBag.GetValue<string>("marker"));
        Assert.Equal("v1", branchB.StateBag.GetValue<string>("marker"));

        // Mutating one branch must not affect the other branch or the stored snapshot.
        branchA.StateBag.SetValue("marker", "mutated");
        Assert.Equal("v1", branchB.StateBag.GetValue<string>("marker"));

        AgentSession branchC = await store.GetSessionAsync(agent, "s1");
        Assert.Equal("v1", branchC.StateBag.GetValue<string>("marker"));
    }

    private sealed class TestAgentSession : AgentSession;

    private sealed class ConcreteAgentSessionStore : AgentSessionStore
    {
        public override ValueTask SaveSessionAsync(AIAgent agent, string sessionStoreId, AgentSession session, CancellationToken cancellationToken = default)
            => default;

        public override ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string sessionStoreId, CancellationToken cancellationToken = default)
            => new(new TestAgentSession());

        public override ValueTask DeleteSessionAsync(AIAgent agent, string sessionStoreId, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
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
