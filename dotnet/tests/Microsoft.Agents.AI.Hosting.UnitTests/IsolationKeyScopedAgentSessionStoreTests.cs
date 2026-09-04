// Copyright (c) Microsoft. All rights reserved.

using System;
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
                    actual.Partitions["isolation"] == TestIsolationKey),
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
                    actual.Partitions["isolation"] == TestIsolationKey),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((AgentSession?)null);
        var store = this.CreateStore(TestIsolationKey);

        // Act
        await store.GetSessionAsync(this._agentMock.Object, key);

        // Assert
        this._innerStoreMock.VerifyAll();
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
}
