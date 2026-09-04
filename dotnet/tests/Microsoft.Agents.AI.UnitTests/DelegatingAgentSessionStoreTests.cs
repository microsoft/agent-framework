// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="DelegatingAgentSessionStore"/> class.
/// </summary>
public class DelegatingAgentSessionStoreTests
{
    private readonly Mock<AgentSessionStore> _innerStoreMock;
    private readonly Mock<AIAgent> _agentMock;
    private readonly TestDelegatingAgentSessionStore _delegatingStore;
    private readonly AgentSession _testSession;

    /// <summary>
    /// Initializes a new instance of the <see cref="DelegatingAgentSessionStoreTests"/> class.
    /// </summary>
    public DelegatingAgentSessionStoreTests()
    {
        this._innerStoreMock = new Mock<AgentSessionStore>();
        this._agentMock = new Mock<AIAgent>();
        this._testSession = new TestAgentSession();

        // Setup inner store mock
        this._innerStoreMock
            .Setup(x => x.GetSessionAsync(
                It.IsAny<AIAgent>(),
                It.IsAny<AgentSessionStoreKey>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(this._testSession);

        this._innerStoreMock
            .Setup(x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.IsAny<AgentSessionStoreKey>(),
                It.IsAny<AgentSession>(),
                It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));

        this._delegatingStore = new TestDelegatingAgentSessionStore(this._innerStoreMock.Object);
    }

    #region Constructor Tests

    /// <summary>
    /// Verify that constructor throws ArgumentNullException when innerStore is null.
    /// </summary>
    [Fact]
    public void RequiresInnerStore() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>("innerStore", () => new TestDelegatingAgentSessionStore(null!));

    /// <summary>
    /// Verify that constructor sets the inner store correctly.
    /// </summary>
    [Fact]
    public void Constructor_WithValidInnerStore_SetsInnerStore()
    {
        // Act
        var delegatingStore = new TestDelegatingAgentSessionStore(this._innerStoreMock.Object);

        // Assert
        Assert.Same(this._innerStoreMock.Object, delegatingStore.InnerStore);
    }

    #endregion

    #region Method Delegation Tests

    /// <summary>
    /// Verify that GetSessionAsync delegates to inner store with correct parameters.
    /// </summary>
    [Fact]
    public async Task GetSessionAsyncDelegatesToInnerStoreAsync()
    {
        // Arrange
        var expectedKey = new AgentSessionStoreKey("test-conversation-id").WithPartition("user", "test-user-id");
        var expectedCancellationToken = new CancellationToken();

        this._innerStoreMock
            .Setup(x => x.GetSessionAsync(
                It.Is<AIAgent>(a => a == this._agentMock.Object),
                It.Is<AgentSessionStoreKey>(key => key.Equals(expectedKey)),
                It.Is<CancellationToken>(ct => ct == expectedCancellationToken)))
            .ReturnsAsync(this._testSession);

        // Act
        var session = await this._delegatingStore.GetSessionAsync(
            this._agentMock.Object,
            expectedKey,
            expectedCancellationToken);

        // Assert
        Assert.Same(this._testSession, session);
        this._innerStoreMock.Verify(
            x => x.GetSessionAsync(
                this._agentMock.Object,
                expectedKey,
                expectedCancellationToken),
            Times.Once);
    }

    /// <summary>
    /// Verify that SaveSessionAsync delegates to inner store with correct parameters.
    /// </summary>
    [Fact]
    public async Task SaveSessionAsyncDelegatesToInnerStoreAsync()
    {
        // Arrange
        var expectedKey = new AgentSessionStoreKey("test-conversation-id").WithPartition("user", "test-user-id");
        var expectedCancellationToken = new CancellationToken();
        var expectedSession = new TestAgentSession();

        this._innerStoreMock
            .Setup(x => x.SaveSessionAsync(
                It.Is<AIAgent>(a => a == this._agentMock.Object),
                It.Is<AgentSessionStoreKey>(key => key.Equals(expectedKey)),
                It.Is<AgentSession>(s => s == expectedSession),
                It.Is<CancellationToken>(ct => ct == expectedCancellationToken)))
            .Returns(default(ValueTask));

        // Act
        await this._delegatingStore.SaveSessionAsync(
            this._agentMock.Object,
            expectedKey,
            expectedSession,
            expectedCancellationToken);

        // Assert
        this._innerStoreMock.Verify(
            x => x.SaveSessionAsync(
                this._agentMock.Object,
                expectedKey,
                expectedSession,
                expectedCancellationToken),
            Times.Once);
    }

    /// <summary>
    /// Verify that GetSessionAsync awaits the inner store's result before returning.
    /// </summary>
    [Fact]
    public async Task GetSessionAsyncAwaitsInnerStoreResultAsync()
    {
        // Arrange
        var expectedKey = new AgentSessionStoreKey("test-conversation-id");
        var taskCompletionSource = new TaskCompletionSource<AgentSession?>();

        var innerStoreMock = new Mock<AgentSessionStore>();
        innerStoreMock
            .Setup(x => x.GetSessionAsync(
                It.IsAny<AIAgent>(),
                It.IsAny<AgentSessionStoreKey>(),
                It.IsAny<CancellationToken>()))
            .Returns(new ValueTask<AgentSession?>(taskCompletionSource.Task));

        var delegatingStore = new TestDelegatingAgentSessionStore(innerStoreMock.Object);

        // Act
        var resultTask = delegatingStore.GetSessionAsync(this._agentMock.Object, expectedKey);

        // Assert
        Assert.False(resultTask.IsCompleted);
        taskCompletionSource.SetResult(this._testSession);
        Assert.True(resultTask.IsCompleted);
        Assert.Same(this._testSession, await resultTask);
    }

    /// <summary>
    /// Verify that GetOrCreateSessionAsync honors a derived GetSessionAsync override.
    /// </summary>
    [Fact]
    public async Task GetOrCreateSessionAsyncUsesOverriddenGetSessionAsyncAsync()
    {
        // Arrange
        var expectedKey = new AgentSessionStoreKey("test-conversation-id").WithPartition("user", "test-user-id");
        var store = new OverridingGetSessionStore(this._innerStoreMock.Object, this._testSession);

        // Act
        AgentSession session = await store.GetOrCreateSessionAsync(
            this._agentMock.Object,
            expectedKey);

        // Assert
        Assert.Same(this._testSession, session);
        this._innerStoreMock.Verify(
            x => x.GetOrCreateSessionAsync(
                It.IsAny<AIAgent>(),
                It.IsAny<AgentSessionStoreKey>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    /// <summary>
    /// Verify that SaveSessionAsync awaits the inner store's completion before returning.
    /// </summary>
    [Fact]
    public async Task SaveSessionAsyncAwaitsInnerStoreCompletionAsync()
    {
        // Arrange
        var expectedKey = new AgentSessionStoreKey("test-conversation-id");
        var expectedSession = new TestAgentSession();
        var taskCompletionSource = new TaskCompletionSource<bool>();

        var innerStoreMock = new Mock<AgentSessionStore>();
        innerStoreMock
            .Setup(x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.IsAny<AgentSessionStoreKey>(),
                It.IsAny<AgentSession>(),
                It.IsAny<CancellationToken>()))
            .Returns(new ValueTask(taskCompletionSource.Task));

        var delegatingStore = new TestDelegatingAgentSessionStore(innerStoreMock.Object);

        // Act
        var resultTask = delegatingStore.SaveSessionAsync(
            this._agentMock.Object,
            expectedKey,
            expectedSession);

        // Assert
        Assert.False(resultTask.IsCompleted);
        taskCompletionSource.SetResult(true);
        Assert.True(resultTask.IsCompleted);
        await resultTask;
    }

    #endregion

    #region Test Implementation

    /// <summary>
    /// Test implementation of DelegatingAgentSessionStore for testing purposes.
    /// </summary>
    private sealed class TestDelegatingAgentSessionStore(AgentSessionStore innerStore) : DelegatingAgentSessionStore(innerStore)
    {
        public new AgentSessionStore InnerStore => base.InnerStore;
    }

    private sealed class OverridingGetSessionStore(AgentSessionStore innerStore, AgentSession session)
        : DelegatingAgentSessionStore(innerStore)
    {
        public override ValueTask<AgentSession?> GetSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            CancellationToken cancellationToken = default)
            => new(session);
    }

    private sealed class TestAgentSession : AgentSession;

    #endregion
}
