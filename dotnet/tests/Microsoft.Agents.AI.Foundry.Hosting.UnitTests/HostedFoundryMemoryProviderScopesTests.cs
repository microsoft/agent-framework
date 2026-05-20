// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Tests for <see cref="HostedFoundryMemoryProviderScopes"/> built-in stateInitializer factories.
/// </summary>
public class HostedFoundryMemoryProviderScopesTests
{
    private const string TestUserId = "user-isolation-key-1";
    private const string TestChatId = "chat-isolation-key-1";

    [Fact]
    public void PerUser_UsesUserIdAsScope()
    {
        // Arrange
        var session = CreateTaggedSession(TestUserId, TestChatId);
        var initializer = HostedFoundryMemoryProviderScopes.PerUser();

        // Act
        var state = initializer(session);

        // Assert
        Assert.NotNull(state);
        Assert.Equal(TestUserId, state.Scope.Scope);
    }

    [Fact]
    public void PerChat_UsesChatIdAsScope()
    {
        // Arrange
        var session = CreateTaggedSession(TestUserId, TestChatId);
        var initializer = HostedFoundryMemoryProviderScopes.PerChat();

        // Act
        var state = initializer(session);

        // Assert
        Assert.NotNull(state);
        Assert.Equal(TestChatId, state.Scope.Scope);
    }

    [Fact]
    public void PerUserAndChat_ComposesUserAndChatWithColon()
    {
        // Arrange
        var session = CreateTaggedSession(TestUserId, TestChatId);
        var initializer = HostedFoundryMemoryProviderScopes.PerUserAndChat();

        // Act
        var state = initializer(session);

        // Assert
        Assert.NotNull(state);
        Assert.Equal($"{TestUserId}:{TestChatId}", state.Scope.Scope);
    }

    [Fact]
    public void PerUser_NullSession_Throws()
    {
        // Arrange
        var initializer = HostedFoundryMemoryProviderScopes.PerUser();

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() => initializer(null));
        Assert.Contains(nameof(HostedSessionContext), ex.Message);
    }

    [Fact]
    public void PerChat_NullSession_Throws()
    {
        // Arrange
        var initializer = HostedFoundryMemoryProviderScopes.PerChat();

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => initializer(null));
    }

    [Fact]
    public void PerUserAndChat_NullSession_Throws()
    {
        // Arrange
        var initializer = HostedFoundryMemoryProviderScopes.PerUserAndChat();

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => initializer(null));
    }

    [Fact]
    public void PerUser_SessionWithoutHostedContext_Throws()
    {
        // Arrange
        var session = new BareAgentSession();
        var initializer = HostedFoundryMemoryProviderScopes.PerUser();

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() => initializer(session));
        Assert.Contains(nameof(HostedFoundryMemoryProviderScopes), ex.Message);
    }

    private static BareAgentSession CreateTaggedSession(string userId, string chatId)
    {
        var session = new BareAgentSession();
        session.SetHostedContext(new HostedSessionContext(userId, chatId));
        return session;
    }

    private sealed class BareAgentSession : AgentSession
    {
        public BareAgentSession() : base(new AgentSessionStateBag()) { }
    }
}
