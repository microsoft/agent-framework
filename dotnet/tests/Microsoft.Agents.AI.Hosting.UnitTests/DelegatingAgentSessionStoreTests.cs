// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

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
            .Setup(x => x.GetSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(this._testSession);

        this._innerStoreMock
            .Setup(x => x.SaveSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<AgentSession>(), It.IsAny<CancellationToken>()))
            .Returns(ValueTask.CompletedTask);

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
        const string ExpectedConversationId = "test-conversation-id";
        var expectedCancellationToken = new CancellationToken();

        this._innerStoreMock
            .Setup(x => x.GetSessionAsync(
                It.Is<AIAgent>(a => a == this._agentMock.Object),
                It.Is<string>(c => c == ExpectedConversationId),
                It.Is<CancellationToken>(ct => ct == expectedCancellationToken)))
            .ReturnsAsync(this._testSession);

        // Act
        var session = await this._delegatingStore.GetSessionAsync(
            this._agentMock.Object,
            ExpectedConversationId,
            expectedCancellationToken);

        // Assert
        Assert.Same(this._testSession, session);
        this._innerStoreMock.Verify(
            x => x.GetSessionAsync(
                this._agentMock.Object,
                ExpectedConversationId,
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
        const string ExpectedConversationId = "test-conversation-id";
        var expectedCancellationToken = new CancellationToken();
        var expectedSession = new TestAgentSession();

        this._innerStoreMock
            .Setup(x => x.SaveSessionAsync(
                It.Is<AIAgent>(a => a == this._agentMock.Object),
                It.Is<string>(c => c == ExpectedConversationId),
                It.Is<AgentSession>(s => s == expectedSession),
                It.Is<CancellationToken>(ct => ct == expectedCancellationToken)))
            .Returns(ValueTask.CompletedTask);

        // Act
        await this._delegatingStore.SaveSessionAsync(
            this._agentMock.Object,
            ExpectedConversationId,
            expectedSession,
            expectedCancellationToken);

        // Assert
        this._innerStoreMock.Verify(
            x => x.SaveSessionAsync(
                this._agentMock.Object,
                ExpectedConversationId,
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
        const string ExpectedConversationId = "test-conversation-id";
        var taskCompletionSource = new TaskCompletionSource<AgentSession>();

        var innerStoreMock = new Mock<AgentSessionStore>();
        innerStoreMock
            .Setup(x => x.GetSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .Returns(new ValueTask<AgentSession>(taskCompletionSource.Task));

        var delegatingStore = new TestDelegatingAgentSessionStore(innerStoreMock.Object);

        // Act
        var resultTask = delegatingStore.GetSessionAsync(this._agentMock.Object, ExpectedConversationId);

        // Assert
        Assert.False(resultTask.IsCompleted);
        taskCompletionSource.SetResult(this._testSession);
        Assert.True(resultTask.IsCompleted);
        Assert.Same(this._testSession, await resultTask);
    }

    /// <summary>
    /// Verify that SaveSessionAsync awaits the inner store's completion before returning.
    /// </summary>
    [Fact]
    public async Task SaveSessionAsyncAwaitsInnerStoreCompletionAsync()
    {
        // Arrange
        const string ExpectedConversationId = "test-conversation-id";
        var expectedSession = new TestAgentSession();
        var taskCompletionSource = new TaskCompletionSource();

        var innerStoreMock = new Mock<AgentSessionStore>();
        innerStoreMock
            .Setup(x => x.SaveSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<AgentSession>(), It.IsAny<CancellationToken>()))
            .Returns(new ValueTask(taskCompletionSource.Task));

        var delegatingStore = new TestDelegatingAgentSessionStore(innerStoreMock.Object);

        // Act
        var resultTask = delegatingStore.SaveSessionAsync(this._agentMock.Object, ExpectedConversationId, expectedSession);

        // Assert
        Assert.False(resultTask.IsCompleted);
        taskCompletionSource.SetResult();
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

    private sealed class TestAgentSession : AgentSession;

    #endregion
}
