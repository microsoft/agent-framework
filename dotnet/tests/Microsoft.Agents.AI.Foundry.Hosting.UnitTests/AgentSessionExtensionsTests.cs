// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public sealed class AgentSessionExtensionsTests
{
    [Fact]
    public void GetFoundryHostedUserId_ReturnsNullWhenAbsent()
    {
        // Arrange
        var session = new TestAgentSession();

        // Act
        var userId = session.GetFoundryHostedUserId();

        // Assert
        Assert.Null(userId);
    }

    [Fact]
    public void SetHostedUserId_ThenGetFoundryHostedUserId_RoundTrips()
    {
        // Arrange
        var session = new TestAgentSession();

        // Act
        session.SetHostedUserId("alice");
        var userId = session.GetFoundryHostedUserId();

        // Assert
        Assert.Equal("alice", userId);
    }

    [Fact]
    public void GetFoundryHostedUserId_ReadsExistingStateKey()
    {
        // Arrange
        var session = new TestAgentSession();
        session.StateBag.SetValue("Microsoft.Agents.AI.Foundry.Hosting.HostedUserId", "alice");

        // Act
        var userId = session.GetFoundryHostedUserId();

        // Assert
        Assert.Equal("alice", userId);
    }

    [Fact]
    public void GetFoundryHostedUserId_NullSession_Throws()
    {
        // Arrange
        AgentSession session = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => session.GetFoundryHostedUserId());
    }

    [Fact]
    public void SetHostedUserId_NullOrWhitespace_Throws()
    {
        // Arrange
        var session = new TestAgentSession();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => session.SetHostedUserId(null!));
        Assert.Throws<ArgumentException>(() => session.SetHostedUserId(string.Empty));
        Assert.Throws<ArgumentException>(() => session.SetHostedUserId("   "));
    }

    [Fact]
    public void SetHostedUserId_SecondWrite_Throws()
    {
        // Arrange
        var session = new TestAgentSession();
        session.SetHostedUserId("alice");

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => session.SetHostedUserId("bob"));
    }

    private sealed class TestAgentSession : AgentSession;
}
