// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Tests for <see cref="HostedFoundryMemoryProviderScopes"/> built-in stateInitializer factories.
/// </summary>
public class HostedFoundryMemoryProviderScopesTests
{
    private const string TestUserId = "user-isolation-key-1";

    [Fact]
    public void PerUser_UsesUserIdAsScope()
    {
        // Arrange
        var session = CreateTaggedSession(TestUserId);
        var initializer = HostedFoundryMemoryProviderScopes.PerUser();

        // Act
        var state = initializer(session);

        // Assert
        Assert.NotNull(state);
        Assert.Equal(TestUserId, state.Scope.Scope);
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
    public void PerUser_SessionWithoutHostedContext_Throws()
    {
        // Arrange
        var session = new BareAgentSession();
        var initializer = HostedFoundryMemoryProviderScopes.PerUser();

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() => initializer(session));
        Assert.Contains(nameof(HostedFoundryMemoryProviderScopes), ex.Message);
    }

    private static BareAgentSession CreateTaggedSession(string userId)
    {
        var session = new BareAgentSession();
        session.SetHostedContext(new HostedSessionContext(userId));
        return session;
    }

    private sealed class BareAgentSession : AgentSession
    {
        public BareAgentSession() : base(new AgentSessionStateBag()) { }
    }
}
