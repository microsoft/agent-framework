// Copyright (c) Microsoft. All rights reserved.

using System;

#pragma warning disable CA1861 // Avoid constant arrays as arguments

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Tests for <see cref="AgentSession"/>
/// </summary>
public class AgentSessionTests
{
    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns the session itself when requesting the exact session type.
    /// </summary>
    [Fact]
    public void GetService_RequestingExactThreadType_ReturnsSession()
    {
        // Arrange
        var session = new TestAgentSession();

        // Act
        var result = session.GetService(typeof(TestAgentSession));

        // Assert
        Assert.NotNull(result);
        Assert.Same(session, result);
    }

    /// <summary>
    /// Verify that GetService returns the session itself when requesting the base AgentSession type.
    /// </summary>
    [Fact]
    public void GetService_RequestingAgentSessionType_ReturnsSession()
    {
        // Arrange
        var session = new TestAgentSession();

        // Act
        var result = session.GetService(typeof(AgentSession));

        // Assert
        Assert.NotNull(result);
        Assert.Same(session, result);
    }

    /// <summary>
    /// Verify that GetService returns null when requesting an unrelated type.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnrelatedType_ReturnsNull()
    {
        // Arrange
        var session = new TestAgentSession();

        // Act
        var result = session.GetService(typeof(string));

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService returns null when a service key is provided, even for matching types.
    /// </summary>
    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        // Arrange
        var session = new TestAgentSession();

        // Act
        var result = session.GetService(typeof(TestAgentSession), "some-key");

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService throws ArgumentNullException when serviceType is null.
    /// </summary>
    [Fact]
    public void GetService_WithNullServiceType_ThrowsArgumentNullException()
    {
        // Arrange
        var session = new TestAgentSession();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => session.GetService(null!));
    }

    /// <summary>
    /// Verify that GetService generic method works correctly.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsCorrectType()
    {
        // Arrange
        var session = new TestAgentSession();

        // Act
        var result = session.GetService<TestAgentSession>();

        // Assert
        Assert.NotNull(result);
        Assert.Same(session, result);
    }

    /// <summary>
    /// Verify that GetService generic method returns null for unrelated types.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsNullForUnrelatedType()
    {
        // Arrange
        var session = new TestAgentSession();

        // Act
        var result = session.GetService<string>();

        // Assert
        Assert.Null(result);
    }

    #endregion

    private sealed class TestAgentSession : AgentSession;
}
