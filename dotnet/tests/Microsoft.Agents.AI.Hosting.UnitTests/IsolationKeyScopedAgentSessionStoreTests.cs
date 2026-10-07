// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="IsolationKeyScopedAgentSessionStore"/>.
/// </summary>
public class IsolationKeyScopedAgentSessionStoreTests
{
    private const string TestIsolationKey = "test-key";

    private readonly Mock<AgentSessionStore> _innerStoreMock = new();
    private readonly Mock<AIAgent> _agentMock = new();

    [Fact]
    public void RequiresInnerStore()
    {
        // Arrange
        var provider = new TestAgentIsolationKeyProvider(TestIsolationKey);

        // Act and assert
        Assert.Throws<ArgumentNullException>("innerStore", () =>
            new IsolationKeyScopedAgentSessionStore(null!, provider));
    }

    [Fact]
    public async Task GetSessionAsync_AddsIsolationPartitionAsync()
    {
        // Arrange
        var expectedSession = new TestAgentSession();
        var key = new AgentSessionStoreKey("session-1").WithPartition("tenant", "tenant-1");
        this._innerStoreMock
            .Setup(x => x.GetSessionAsync(
                this._agentMock.Object,
                It.Is<AgentSessionStoreKey>(actual =>
                    actual.SessionId == "session-1"
                    && actual.Partitions != null
                    && actual.Partitions["tenant"] == "tenant-1"
                    && actual.Partitions["isolation"] == TestIsolationKey),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedSession);
        var store = this.CreateStore(TestIsolationKey);

        // Act
        AgentSession? session = await store.GetSessionAsync(this._agentMock.Object, key);

        // Assert
        Assert.Same(expectedSession, session);
        this._innerStoreMock.VerifyAll();
    }

    [Fact]
    public async Task SaveSessionAsync_AddsIsolationPartitionAsync()
    {
        // Arrange
        var key = new AgentSessionStoreKey("session-1");
        var session = new TestAgentSession();
        this._innerStoreMock
            .Setup(x => x.SaveSessionAsync(
                this._agentMock.Object,
                It.Is<AgentSessionStoreKey>(actual =>
                    actual.SessionId == "session-1"
                    && actual.Partitions != null
                    && actual.Partitions["isolation"] == TestIsolationKey),
                session,
                It.IsAny<CancellationToken>()))
            .Returns(ValueTask.CompletedTask);
        var store = this.CreateStore(TestIsolationKey);

        // Act
        await store.SaveSessionAsync(this._agentMock.Object, key, session);

        // Assert
        this._innerStoreMock.VerifyAll();
    }

    [Fact]
    public async Task GetOrCreateSessionAsync_ForwardsScopedKeyToSpecializedInnerStoreAsync()
    {
        // Arrange
        var expectedSession = new TestAgentSession();
        var key = new AgentSessionStoreKey("session-1");
        this._innerStoreMock
            .Setup(x => x.GetOrCreateSessionAsync(
                this._agentMock.Object,
                It.Is<AgentSessionStoreKey>(actual =>
                    actual.Partitions != null && actual.Partitions["isolation"] == TestIsolationKey),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedSession);
        var store = this.CreateStore(TestIsolationKey);

        // Act
        AgentSession session = await store.GetOrCreateSessionAsync(this._agentMock.Object, key);

        // Assert
        Assert.Same(expectedSession, session);
        this._innerStoreMock.VerifyAll();
    }

    [Fact]
    public async Task GetSessionAsync_StrictModeWithoutIsolationKey_ThrowsAsync()
    {
        // Arrange
        var store = this.CreateStore(
            isolationKey: null,
            new IsolationKeyScopedAgentSessionStoreOptions { Strict = true });

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => store.GetSessionAsync(
                this._agentMock.Object,
                new AgentSessionStoreKey("session-1")).AsTask());

        // Assert
        Assert.Contains("Agent isolation key is required", exception.Message);
    }

    [Fact]
    public async Task GetSessionAsync_NonStrictModePreservesExistingPartitionsAsync()
    {
        // Arrange
        var key = new AgentSessionStoreKey("session-1").WithPartition("tenant", "tenant-1");
        this._innerStoreMock
            .Setup(x => x.GetSessionAsync(
                this._agentMock.Object,
                key,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((AgentSession?)null);
        var store = this.CreateStore(
            isolationKey: null,
            new IsolationKeyScopedAgentSessionStoreOptions { Strict = false });

        // Act
        await store.GetSessionAsync(this._agentMock.Object, key);

        // Assert
        this._innerStoreMock.VerifyAll();
    }

    [Fact]
    public async Task GetSessionAsync_IsolationProviderReplacesExistingIsolationPartitionAsync()
    {
        // Arrange
        var key = new AgentSessionStoreKey("session-1").WithPartition("isolation", "caller-value");
        this._innerStoreMock
            .Setup(x => x.GetSessionAsync(
                this._agentMock.Object,
                It.Is<AgentSessionStoreKey>(actual =>
                    actual.Partitions != null && actual.Partitions["isolation"] == TestIsolationKey),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((AgentSession?)null);
        var store = this.CreateStore(TestIsolationKey);

        // Act
        await store.GetSessionAsync(this._agentMock.Object, key);

        // Assert
        this._innerStoreMock.VerifyAll();
    }

    [Fact]
    public async Task BindIsolationKey_NestedIsolationStore_UsesCapturedKeyAsync()
    {
        // Arrange
        var expectedSession = new TestAgentSession();
        var recordingStore = new RecordingSessionStore(expectedSession);
        var isolationStore = new IsolationKeyScopedAgentSessionStore(
            recordingStore,
            new TestAgentIsolationKeyProvider(key: null),
            new IsolationKeyScopedAgentSessionStoreOptions { Strict = true });
        var outerStore = new TestDelegatingAgentSessionStore(isolationStore);
        var hostAgent = new AIHostAgent(this._agentMock.Object, outerStore);

        // Act
        AIHostAgent boundAgent = hostAgent.BindIsolationKey("captured-user");
        AgentSession session = await boundAgent.GetOrCreateSessionAsync("session-1");

        // Assert
        Assert.Same(expectedSession, session);
        Assert.Equal(1, outerStore.GetSessionCount);
        AgentSessionStoreKey key = Assert.Single(recordingStore.Keys);
        Assert.Equal("captured-user", key.Partitions!["isolation"]);
    }

    [Fact]
    public async Task BindIsolationKey_ConcurrentOperations_KeepCapturedKeysSeparateAsync()
    {
        // Arrange
        var recordingStore = new RecordingSessionStore(session: null);
        var isolationStore = new IsolationKeyScopedAgentSessionStore(
            recordingStore,
            new TestAgentIsolationKeyProvider(key: null),
            new IsolationKeyScopedAgentSessionStoreOptions { Strict = true });
        var outerStore = new PausingDelegatingAgentSessionStore(isolationStore);
        var hostAgent = new AIHostAgent(this._agentMock.Object, outerStore);
        AIHostAgent aliceAgent = hostAgent.BindIsolationKey("alice");
        AIHostAgent bobAgent = hostAgent.BindIsolationKey("bob");
        var session = new TestAgentSession();

        // Act
        await Task.WhenAll(
            aliceAgent.SaveSessionAsync("alice-session", session).AsTask(),
            bobAgent.SaveSessionAsync("bob-session", session).AsTask());

        // Assert
        Assert.Equal(2, outerStore.SaveSessionCount);
        Assert.Contains(
            recordingStore.Keys,
            key => key.SessionId == "alice-session" && key.Partitions!["isolation"] == "alice");
        Assert.Contains(
            recordingStore.Keys,
            key => key.SessionId == "bob-session" && key.Partitions!["isolation"] == "bob");
    }

    private IsolationKeyScopedAgentSessionStore CreateStore(
        string? isolationKey,
        IsolationKeyScopedAgentSessionStoreOptions? options = null)
        => new(
            this._innerStoreMock.Object,
            new TestAgentIsolationKeyProvider(isolationKey),
            options);

    private sealed class TestAgentIsolationKeyProvider(string? key) : AgentIsolationKeyProvider
    {
        public override ValueTask<string?> GetIsolationKeyAsync(CancellationToken cancellationToken = default)
            => new(key);
    }

    private sealed class TestAgentSession : AgentSession;

    private sealed class TestDelegatingAgentSessionStore(AgentSessionStore innerStore)
        : DelegatingAgentSessionStore(innerStore)
    {
        public int GetSessionCount { get; private set; }

        public override ValueTask<AgentSession?> GetSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            CancellationToken cancellationToken = default)
        {
            this.GetSessionCount++;
            return base.GetSessionAsync(agent, key, cancellationToken);
        }
    }

    private sealed class PausingDelegatingAgentSessionStore(AgentSessionStore innerStore)
        : DelegatingAgentSessionStore(innerStore)
    {
        private readonly TaskCompletionSource _bothSavesStarted =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _saveSessionCount;

        public int SaveSessionCount => this._saveSessionCount;

        public override async ValueTask SaveSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            AgentSession session,
            CancellationToken cancellationToken = default)
        {
            if (Interlocked.Increment(ref this._saveSessionCount) == 2)
            {
                this._bothSavesStarted.TrySetResult();
            }

            await this._bothSavesStarted.Task.WaitAsync(cancellationToken);
            await base.SaveSessionAsync(agent, key, session, cancellationToken);
        }
    }

    private sealed class RecordingSessionStore(AgentSession? session) : AgentSessionStore
    {
        public ConcurrentBag<AgentSessionStoreKey> Keys { get; } = [];

        public override ValueTask<AgentSession?> GetSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            CancellationToken cancellationToken = default)
        {
            this.Keys.Add(key);
            return new(session);
        }

        public override ValueTask SaveSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            AgentSession session,
            CancellationToken cancellationToken = default)
        {
            this.Keys.Add(key);
            return ValueTask.CompletedTask;
        }
    }
}
