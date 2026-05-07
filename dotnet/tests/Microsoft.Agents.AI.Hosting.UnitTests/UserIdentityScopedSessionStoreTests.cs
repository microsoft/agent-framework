// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Unit tests for the <see cref="UserIdentityScopedSessionStore"/> class.
/// </summary>
public class UserIdentityScopedSessionStoreTests
{
    private const string TestUserId = "test-user-id";
    private const string TestConversationId = "test-conversation-id";
    private const string CustomClaimType = "custom-claim-type";
    private const string CustomClaimValue = "custom-claim-value";
    private const string User1 = "user-1";
    private const string User2 = "user-2";

    private readonly Mock<AgentSessionStore> _innerStoreMock;
    private readonly Mock<AIAgent> _agentMock;
    private readonly Mock<IHttpContextAccessor> _httpContextAccessorMock;
    private readonly AgentSession _testSession;

    /// <summary>
    /// Initializes a new instance of the <see cref="UserIdentityScopedSessionStoreTests"/> class.
    /// </summary>
    public UserIdentityScopedSessionStoreTests()
    {
        this._innerStoreMock = new Mock<AgentSessionStore>();
        this._agentMock = new Mock<AIAgent>();
        this._httpContextAccessorMock = new Mock<IHttpContextAccessor>();
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
    public void RequiresInnerStore() =>
        Assert.Throws<ArgumentNullException>("innerStore", () => new UserIdentityScopedSessionStore(null!, this._httpContextAccessorMock.Object));

    /// <summary>
    /// Verify that constructor accepts null IHttpContextAccessor.
    /// </summary>
    [Fact]
    public void Constructor_WithNullHttpContextAccessor_DoesNotThrow()
    {
        // Act & Assert - should not throw
        var store = new UserIdentityScopedSessionStore(this._innerStoreMock.Object, contextAccessor: null, strict: false);
        Assert.NotNull(store);
    }

    #endregion

    #region GetSessionAsync Tests

    /// <summary>
    /// Verify that GetSessionAsync scopes the conversation ID with the user's claim value.
    /// </summary>
    [Fact]
    public async Task GetSessionAsyncScopesConversationIdWithUserClaimAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim(ClaimsIdentity.DefaultNameClaimType, TestUserId);
        var store = new UserIdentityScopedSessionStore(this._innerStoreMock.Object, this._httpContextAccessorMock.Object);

        // Act
        await store.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert
        this._innerStoreMock.Verify(
            x => x.GetSessionAsync(
                this._agentMock.Object,
                $"{TestUserId}:{TestConversationId}",
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that GetSessionAsync uses custom claim type when specified.
    /// </summary>
    [Fact]
    public async Task GetSessionAsyncUsesCustomClaimTypeAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim(CustomClaimType, CustomClaimValue);
        var store = new UserIdentityScopedSessionStore(
            this._innerStoreMock.Object,
            this._httpContextAccessorMock.Object,
            claimType: CustomClaimType);

        // Act
        await store.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert
        this._innerStoreMock.Verify(
            x => x.GetSessionAsync(
                this._agentMock.Object,
                $"{CustomClaimValue}:{TestConversationId}",
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that GetSessionAsync throws InvalidOperationException when claim is missing in strict mode.
    /// </summary>
    [Fact]
    public async Task GetSessionAsyncThrowsWhenClaimMissingInStrictModeAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim("other-claim", "value");
        var store = new UserIdentityScopedSessionStore(
            this._innerStoreMock.Object,
            this._httpContextAccessorMock.Object,
            strict: true);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await store.GetSessionAsync(this._agentMock.Object, TestConversationId));

        Assert.Contains(ClaimsIdentity.DefaultNameClaimType, exception.Message);
    }

    /// <summary>
    /// Verify that GetSessionAsync does not throw when claim is missing in non-strict mode.
    /// </summary>
    [Fact]
    public async Task GetSessionAsyncDoesNotThrowWhenClaimMissingInNonStrictModeAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim("other-claim", "value");
        var store = new UserIdentityScopedSessionStore(
            this._innerStoreMock.Object,
            this._httpContextAccessorMock.Object,
            strict: false);

        // Act - should not throw
        await store.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert - conversation ID should use null scope
        this._innerStoreMock.Verify(
            x => x.GetSessionAsync(
                this._agentMock.Object,
                $":{TestConversationId}",
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
        this.SetupHttpContextWithClaim(ClaimsIdentity.DefaultNameClaimType, TestUserId);
        var store = new UserIdentityScopedSessionStore(this._innerStoreMock.Object, this._httpContextAccessorMock.Object);

        // Act
        var result = await store.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert
        Assert.Same(this._testSession, result);
    }

    #endregion

    #region SaveSessionAsync Tests

    /// <summary>
    /// Verify that SaveSessionAsync scopes the conversation ID with the user's claim value.
    /// </summary>
    [Fact]
    public async Task SaveSessionAsyncScopesConversationIdWithUserClaimAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim(ClaimsIdentity.DefaultNameClaimType, TestUserId);
        var store = new UserIdentityScopedSessionStore(this._innerStoreMock.Object, this._httpContextAccessorMock.Object);
        var sessionToSave = new TestAgentSession();

        // Act
        await store.SaveSessionAsync(this._agentMock.Object, TestConversationId, sessionToSave);

        // Assert
        this._innerStoreMock.Verify(
            x => x.SaveSessionAsync(
                this._agentMock.Object,
                $"{TestUserId}:{TestConversationId}",
                sessionToSave,
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that SaveSessionAsync uses custom claim type when specified.
    /// </summary>
    [Fact]
    public async Task SaveSessionAsyncUsesCustomClaimTypeAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim(CustomClaimType, CustomClaimValue);
        var store = new UserIdentityScopedSessionStore(
            this._innerStoreMock.Object,
            this._httpContextAccessorMock.Object,
            claimType: CustomClaimType);
        var sessionToSave = new TestAgentSession();

        // Act
        await store.SaveSessionAsync(this._agentMock.Object, TestConversationId, sessionToSave);

        // Assert
        this._innerStoreMock.Verify(
            x => x.SaveSessionAsync(
                this._agentMock.Object,
                $"{CustomClaimValue}:{TestConversationId}",
                sessionToSave,
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that SaveSessionAsync throws InvalidOperationException when claim is missing in strict mode.
    /// </summary>
    [Fact]
    public async Task SaveSessionAsyncThrowsWhenClaimMissingInStrictModeAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim("other-claim", "value");
        var store = new UserIdentityScopedSessionStore(
            this._innerStoreMock.Object,
            this._httpContextAccessorMock.Object,
            strict: true);
        var sessionToSave = new TestAgentSession();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await store.SaveSessionAsync(this._agentMock.Object, TestConversationId, sessionToSave));

        Assert.Contains(ClaimsIdentity.DefaultNameClaimType, exception.Message);
    }

    /// <summary>
    /// Verify that SaveSessionAsync does not throw when claim is missing in non-strict mode.
    /// </summary>
    [Fact]
    public async Task SaveSessionAsyncDoesNotThrowWhenClaimMissingInNonStrictModeAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim("other-claim", "value");
        var store = new UserIdentityScopedSessionStore(
            this._innerStoreMock.Object,
            this._httpContextAccessorMock.Object,
            strict: false);
        var sessionToSave = new TestAgentSession();

        // Act - should not throw
        await store.SaveSessionAsync(this._agentMock.Object, TestConversationId, sessionToSave);

        // Assert - conversation ID should use null scope
        this._innerStoreMock.Verify(
            x => x.SaveSessionAsync(
                this._agentMock.Object,
                $":{TestConversationId}",
                sessionToSave,
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    #endregion

    #region Edge Cases

    /// <summary>
    /// Verify behavior when HttpContextAccessor returns null HttpContext.
    /// </summary>
    [Fact]
    public async Task WhenHttpContextIsNullAndStrictThrowsAsync()
    {
        // Arrange
        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns((HttpContext?)null);
        var store = new UserIdentityScopedSessionStore(
            this._innerStoreMock.Object,
            this._httpContextAccessorMock.Object,
            strict: true);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await store.GetSessionAsync(this._agentMock.Object, TestConversationId));
    }

    /// <summary>
    /// Verify behavior when HttpContextAccessor returns null HttpContext in non-strict mode.
    /// </summary>
    [Fact]
    public async Task WhenHttpContextIsNullAndNonStrictProceedsAsync()
    {
        // Arrange
        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns((HttpContext?)null);
        var store = new UserIdentityScopedSessionStore(
            this._innerStoreMock.Object,
            this._httpContextAccessorMock.Object,
            strict: false);

        // Act - should not throw
        await store.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert
        this._innerStoreMock.Verify(
            x => x.GetSessionAsync(
                this._agentMock.Object,
                $":{TestConversationId}",
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that different users get different scoped conversation IDs.
    /// </summary>
    [Fact]
    public async Task DifferentUsersGetDifferentScopedConversationIdsAsync()
    {
        // Arrange
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

        // Act - User 1
        this.SetupHttpContextWithClaim(ClaimsIdentity.DefaultNameClaimType, User1);
        var store1 = new UserIdentityScopedSessionStore(this._innerStoreMock.Object, this._httpContextAccessorMock.Object);
        await store1.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Act - User 2
        this.SetupHttpContextWithClaim(ClaimsIdentity.DefaultNameClaimType, User2);
        var store2 = new UserIdentityScopedSessionStore(this._innerStoreMock.Object, this._httpContextAccessorMock.Object);
        await store2.GetSessionAsync(this._agentMock.Object, TestConversationId);

        // Assert
        Assert.Equal($"{User1}:{TestConversationId}", capturedConversationId1);
        Assert.Equal($"{User2}:{TestConversationId}", capturedConversationId2);
        Assert.NotEqual(capturedConversationId1, capturedConversationId2);
    }

    #endregion

    #region Helper Methods

    private void SetupHttpContextWithClaim(string claimType, string claimValue)
    {
        var claims = new[] { new Claim(claimType, claimValue) };
        var identity = new ClaimsIdentity(claims);
        var principal = new ClaimsPrincipal(identity);

        var httpContext = new DefaultHttpContext
        {
            User = principal
        };

        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns(httpContext);
    }

    private sealed class TestAgentSession : AgentSession;

    #endregion
}
