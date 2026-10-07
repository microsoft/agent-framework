// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentSessionStore"/>.
/// </summary>
public sealed class AgentSessionStoreTests
{
    [Fact]
    public void GetService_CompatibleUnkeyedType_ReturnsStore()
    {
        // Arrange
        var store = new TestAgentSessionStore(session: null);

        // Act and assert
        Assert.Same(store, store.GetService(typeof(TestAgentSessionStore)));
        Assert.Same(store, store.GetService<AgentSessionStore>());
        Assert.Same(store, store.GetService<object>());
    }

    [Fact]
    public void GetService_UnsupportedRequest_ReturnsDefault()
    {
        // Arrange
        var store = new TestAgentSessionStore(session: null);

        // Act and assert
        Assert.Null(store.GetService(typeof(IDisposable)));
        Assert.Null(store.GetService<IDisposable>());
        Assert.Null(store.GetService<AgentSessionStore>("key"));
        Assert.Equal(0, store.GetService<int>());
    }

    [Fact]
    public void GetService_NullType_Throws()
    {
        // Arrange
        var store = new TestAgentSessionStore(session: null);

        // Act and assert
        Assert.Throws<ArgumentNullException>("serviceType", () => store.GetService(null!));
    }

    [Fact]
    public void GetService_GenericOverload_UsesVirtualMethod()
    {
        // Arrange
        var service = new object();
        var key = new object();
        var store = new Mock<AgentSessionStore>();
        store.Setup(s => s.GetService(typeof(object), key)).Returns(service);

        // Act
        var result = store.Object.GetService<object>(key);

        // Assert
        Assert.Same(service, result);
        store.Verify(s => s.GetService(typeof(object), key), Times.Once);
    }

    [Fact]
    public async Task GetOrCreateSessionAsync_StoredSession_ReturnsStoredSessionAsync()
    {
        // Arrange
        var storedSession = new TestAgentSession();
        var store = new TestAgentSessionStore(storedSession);
        var agent = new Mock<AIAgent>();
        var key = new AgentSessionStoreKey("conversation-1").WithPartition("user", "user-1");

        // Act
        AgentSession session = await store.GetOrCreateSessionAsync(agent.Object, key);

        // Assert
        Assert.Same(storedSession, session);
        Assert.Same(key, store.LastKey);
        agent.Protected().Verify(
            "CreateSessionCoreAsync",
            Times.Never(),
            ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public async Task GetOrCreateSessionAsync_MissingSession_CreatesSessionAsync()
    {
        // Arrange
        var createdSession = new TestAgentSession();
        var store = new TestAgentSessionStore(session: null);
        var agent = new Mock<AIAgent>();
        var key = new AgentSessionStoreKey("conversation-1");
        agent.Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(createdSession);

        // Act
        AgentSession session = await store.GetOrCreateSessionAsync(agent.Object, key);

        // Assert
        Assert.Same(createdSession, session);
        agent.Protected().Verify(
            "CreateSessionCoreAsync",
            Times.Once(),
            ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public async Task GetOrCreateSessionAsync_NullAgent_ThrowsAsync()
    {
        // Arrange
        var store = new TestAgentSessionStore(session: null);

        // Act and assert
        await Assert.ThrowsAsync<ArgumentNullException>(
            () => store.GetOrCreateSessionAsync(null!, new AgentSessionStoreKey("conversation-1")).AsTask());
    }

    private sealed class TestAgentSessionStore(AgentSession? session) : AgentSessionStore
    {
        public AgentSessionStoreKey? LastKey { get; private set; }

        public override ValueTask<AgentSession?> GetSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            CancellationToken cancellationToken = default)
        {
            this.LastKey = key;
            return new(session);
        }

        public override ValueTask SaveSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            AgentSession session,
            CancellationToken cancellationToken = default)
            => default;
    }

    private sealed class TestAgentSession : AgentSession;
}
