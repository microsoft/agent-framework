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
    private const string TestConversationId = "test-conversation-id";

    private readonly Mock<AgentSessionStore> _innerStoreMock;
    private readonly Mock<AIAgent> _agentMock;
    private readonly AgentSession _testSession;

    /// <summary>
    /// Initializes a new instance of the <see cref="IsolationKeyScopedAgentSessionStoreTests"/> class.
    /// </summary>
    public IsolationKeyScopedAgentSessionStoreTests()
    {
        this._innerStoreMock = new Mock<AgentSessionStore>();
        this._agentMock = new Mock<AIAgent>();
        this._testSession = new TestAgentSession();

        this._innerStoreMock
            .Setup(x => x.GetSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(this._testSession);

        this._innerStoreMock
            .Setup(x => x.SaveSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<AgentSession>(), It.IsAny<CancellationToken>()))
            .Returns(ValueTask.CompletedTask);
    }

    #region Constructor Tests

    /// <summary>
    /// Verify that constructor throws ArgumentNullException when innerStore is null.
    /// </summary>
    [Fact]
    public void RequiresInnerStore()
    {
        // Arrange
        var provider = new TestSessionIsolationKeyProvider(TestIsolationKey);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("innerStore", () =>
            new IsolationKeyScopedAgentSessionStore(null!, provider));
    }

    /// <summary>
    /// Verify that constructor throws ArgumentNullException when keyProvider is null.
    /// </summary>
    [Fact]
    public void RequiresKeyProvider()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("keyProvider", () =>
            new IsolationKeyScopedAgentSessionStore(this._innerStoreMock.Object, null!));
    }

    /// <summary>
    /// Verify that constructor uses default options when options is null.
    /// </summary>
    [Fact]
    public void UsesDefaultOptionsWhenNull()
    {
        // Arrange
        var provider = new TestSessionIsolationKeyProvider(TestIsolationKey);

        // Act & Assert - should not throw
        var store = new IsolationKeyScopedAgentSessionStore(this._innerStoreMock.Object, provider, options: null);
        Assert.NotNull(store);
    }

    #endregion

    #region GetSessionAsync Tests

    /// <summary>
    /// Verify that GetSessionAsync scopes the conversation ID with the isolation key.
    /// </summary>
    [Fact]
    public async Task GetSessionAsyncScopesConversationIdWithKeyAsync()
    {
        // Arrange
        var provider = new TestSessionIsolationKeyProvider(TestIsolationKey);
        var store = new IsolationKeyScopedAgentSessionStore(this._innerStoreMock.Object, provider);

        // Act
        await store.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert
        this._innerStoreMock.Verify(
            x => x.GetSessionAsync(
                this._agentMock.Object,
                $"{TestIsolationKey}::{TestConversationId}",
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that GetSessionAsync throws InvalidOperationException when key is null in strict mode.
    /// </summary>
    [Fact]
    public async Task GetSessionAsyncThrowsWhenKeyNullInStrictModeAsync()
    {
        // Arrange
        var provider = new TestSessionIsolationKeyProvider(null);
        var store = new IsolationKeyScopedAgentSessionStore(
            this._innerStoreMock.Object,
            provider,
            new IsolationKeyScopedAgentSessionStoreOptions { Strict = true });

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await store.GetSessionAsync(this._agentMock.Object, TestConversationId));

        Assert.Contains("Session isolation key is required", exception.Message);
    }

    /// <summary>
    /// Verify that GetSessionAsync does not throw when key is null in non-strict mode.
    /// </summary>
    [Fact]
    public async Task GetSessionAsyncDoesNotThrowWhenKeyNullInNonStrictModeAsync()
    {
        // Arrange
        var provider = new TestSessionIsolationKeyProvider(null);
        var store = new IsolationKeyScopedAgentSessionStore(
            this._innerStoreMock.Object,
            provider,
            new IsolationKeyScopedAgentSessionStoreOptions { Strict = false });

        // Act - should not throw
        await store.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert - conversation ID should be passed through unmodified
        this._innerStoreMock.Verify(
            x => x.GetSessionAsync(
                this._agentMock.Object,
                TestConversationId,
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that GetSessionAsync returns the session from the inner store.
    /// </summary>
    [Fact]
    public async Task GetSessionAsyncReturnsSessionFromInnerStoreAsync()
    {
        // Arrange
        var provider = new TestSessionIsolationKeyProvider(TestIsolationKey);
        var store = new IsolationKeyScopedAgentSessionStore(this._innerStoreMock.Object, provider);

        // Act
        var result = await store.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert
        Assert.Same(this._testSession, result);
    }

    #endregion

    #region SaveSessionAsync Tests

    /// <summary>
    /// Verify that SaveSessionAsync scopes the conversation ID with the isolation key.
    /// </summary>
    [Fact]
    public async Task SaveSessionAsyncScopesConversationIdWithKeyAsync()
    {
        // Arrange
        var provider = new TestSessionIsolationKeyProvider(TestIsolationKey);
        var store = new IsolationKeyScopedAgentSessionStore(this._innerStoreMock.Object, provider);
        var sessionToSave = new TestAgentSession();

        // Act
        await store.SaveSessionAsync(this._agentMock.Object, TestConversationId, sessionToSave);

        // Assert
        this._innerStoreMock.Verify(
            x => x.SaveSessionAsync(
                this._agentMock.Object,
                $"{TestIsolationKey}::{TestConversationId}",
                sessionToSave,
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that SaveSessionAsync throws InvalidOperationException when key is null in strict mode.
    /// </summary>
    [Fact]
    public async Task SaveSessionAsyncThrowsWhenKeyNullInStrictModeAsync()
    {
        // Arrange
        var provider = new TestSessionIsolationKeyProvider(null);
        var store = new IsolationKeyScopedAgentSessionStore(
            this._innerStoreMock.Object,
            provider,
            new IsolationKeyScopedAgentSessionStoreOptions { Strict = true });
        var sessionToSave = new TestAgentSession();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await store.SaveSessionAsync(this._agentMock.Object, TestConversationId, sessionToSave));

        Assert.Contains("Session isolation key is required", exception.Message);
    }

    /// <summary>
    /// Verify that SaveSessionAsync does not throw when key is null in non-strict mode.
    /// </summary>
    [Fact]
    public async Task SaveSessionAsyncDoesNotThrowWhenKeyNullInNonStrictModeAsync()
    {
        // Arrange
        var provider = new TestSessionIsolationKeyProvider(null);
        var store = new IsolationKeyScopedAgentSessionStore(
            this._innerStoreMock.Object,
            provider,
            new IsolationKeyScopedAgentSessionStoreOptions { Strict = false });
        var sessionToSave = new TestAgentSession();

        // Act - should not throw
        await store.SaveSessionAsync(this._agentMock.Object, TestConversationId, sessionToSave);

        // Assert - conversation ID should be passed through unmodified
        this._innerStoreMock.Verify(
            x => x.SaveSessionAsync(
                this._agentMock.Object,
                TestConversationId,
                sessionToSave,
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    #endregion

    #region Escaping Tests

    /// <summary>
    /// Verify that colons in the isolation key are escaped.
    /// </summary>
    [Fact]
    public async Task EscapesColonsInIsolationKeyAsync()
    {
        // Arrange
        const string KeyWithColon = "key:with:colons";
        var provider = new TestSessionIsolationKeyProvider(KeyWithColon);
        var store = new IsolationKeyScopedAgentSessionStore(this._innerStoreMock.Object, provider);

        // Act
        await store.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert - colons should be escaped as \:
        this._innerStoreMock.Verify(
            x => x.GetSessionAsync(
                this._agentMock.Object,
                $"key\\:with\\:colons::{TestConversationId}",
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that backslashes in the isolation key are escaped.
    /// </summary>
    [Fact]
    public async Task EscapesBackslashesInIsolationKeyAsync()
    {
        // Arrange
        const string KeyWithBackslash = @"domain\key";
        var provider = new TestSessionIsolationKeyProvider(KeyWithBackslash);
        var store = new IsolationKeyScopedAgentSessionStore(this._innerStoreMock.Object, provider);

        // Act
        await store.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert - backslashes should be escaped as \\
        this._innerStoreMock.Verify(
            x => x.GetSessionAsync(
                this._agentMock.Object,
                $"domain\\\\key::{TestConversationId}",
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that both backslashes and colons in the isolation key are escaped correctly.
    /// </summary>
    [Fact]
    public async Task EscapesBothBackslashesAndColonsInIsolationKeyAsync()
    {
        // Arrange
        const string KeyWithBoth = @"domain\key:role";
        var provider = new TestSessionIsolationKeyProvider(KeyWithBoth);
        var store = new IsolationKeyScopedAgentSessionStore(this._innerStoreMock.Object, provider);

        // Act
        await store.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert - backslashes escaped first, then colons
        this._innerStoreMock.Verify(
            x => x.GetSessionAsync(
                this._agentMock.Object,
                $"domain\\\\key\\:role::{TestConversationId}",
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    #endregion

    #region Isolation Tests

    /// <summary>
    /// Verify that different isolation keys result in different scoped conversation IDs.
    /// </summary>
    [Fact]
    public async Task DifferentKeysResultInDifferentScopedConversationIdsAsync()
    {
        // Arrange
        const string Key1 = "key-1";
        const string Key2 = "key-2";
        string? capturedConversationId1 = null;
        string? capturedConversationId2 = null;

        this._innerStoreMock
            .Setup(x => x.GetSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .Callback<AIAgent, string, CancellationToken>((_, conversationId, _) =>
            {
                if (capturedConversationId1 == null)
                {
                    capturedConversationId1 = conversationId;
                }
                else
                {
                    capturedConversationId2 = conversationId;
                }
            })
            .ReturnsAsync(this._testSession);

        // Act - Key 1
        var provider1 = new TestSessionIsolationKeyProvider(Key1);
        var store1 = new IsolationKeyScopedAgentSessionStore(this._innerStoreMock.Object, provider1);
        await store1.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Act - Key 2
        var provider2 = new TestSessionIsolationKeyProvider(Key2);
        var store2 = new IsolationKeyScopedAgentSessionStore(this._innerStoreMock.Object, provider2);
        await store2.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert
        Assert.Equal($"{Key1}::{TestConversationId}", capturedConversationId1);
        Assert.Equal($"{Key2}::{TestConversationId}", capturedConversationId2);
        Assert.NotEqual(capturedConversationId1, capturedConversationId2);
    }

    #endregion

    #region GetService Tests

    /// <summary>
    /// Verify that GetService can retrieve IsolationKeyScopedAgentSessionStore from a delegation chain.
    /// </summary>
    [Fact]
    public void GetServiceReturnsIsolationKeyScopedAgentSessionStore()
    {
        // Arrange
        var provider = new TestSessionIsolationKeyProvider(TestIsolationKey);
        var store = new IsolationKeyScopedAgentSessionStore(this._innerStoreMock.Object, provider);

        // Act
        var result = store.GetService<IsolationKeyScopedAgentSessionStore>();

        // Assert
        Assert.Same(store, result);
    }

    /// <summary>
    /// Verify that GetService chains through to find inner store types.
    /// </summary>
    [Fact]
    public void GetServiceChainsToInnerStore()
    {
        // Arrange
        var concreteInnerStore = new ConcreteAgentSessionStore();
        var provider = new TestSessionIsolationKeyProvider(TestIsolationKey);
        var store = new IsolationKeyScopedAgentSessionStore(concreteInnerStore, provider);

        // Act
        var result = store.GetService<ConcreteAgentSessionStore>();

        // Assert
        Assert.Same(concreteInnerStore, result);
    }

    #endregion

    #region Helper Classes

    /// <summary>
    /// Test implementation of <see cref="SessionIsolationKeyProvider"/> for testing purposes.
    /// </summary>
    private sealed class TestSessionIsolationKeyProvider : SessionIsolationKeyProvider
    {
        private readonly string? _key;

        public TestSessionIsolationKeyProvider(string? key)
        {
            this._key = key;
        }

        public override ValueTask<string?> GetSessionIsolationKeyAsync(CancellationToken cancellationToken = default)
        {
            return new ValueTask<string?>(this._key);
        }
    }

    private sealed class TestAgentSession : AgentSession;

    /// <summary>
    /// Concrete (non-delegating) session store for testing GetService chaining.
    /// </summary>
    private sealed class ConcreteAgentSessionStore : AgentSessionStore
    {
        public override ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string conversationId, CancellationToken cancellationToken = default)
            => new(new TestAgentSession());

        public override ValueTask SaveSessionAsync(AIAgent agent, string conversationId, AgentSession session, CancellationToken cancellationToken = default)
            => ValueTask.CompletedTask;
    }

    #endregion
}
