// Copyright (c) Microsoft. All rights reserved.

using System;

#pragma warning disable CA1861 // Avoid constant arrays as arguments

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Tests for <see cref="AgentThread"/>
/// </summary>
public class AgentThreadTests
{
    [Fact]
    public void Serialize_ReturnsDefaultJsonElement()
    {
        var thread = new TestAgentThread();
        var result = thread.Serialize();
        Assert.Equal(default, result);
    }

    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns the thread itself when requesting the exact thread type.
    /// </summary>
    [Fact]
    public void GetService_RequestingExactThreadType_ReturnsThread()
    {
        // Arrange
        var thread = new TestAgentThread();

        // Act
        var result = thread.GetService(typeof(TestAgentThread));

        // Assert
        Assert.NotNull(result);
        Assert.Same(thread, result);
    }

    /// <summary>
    /// Verify that GetService returns the thread itself when requesting the base AgentThread type.
    /// </summary>
    [Fact]
    public void GetService_RequestingAgentThreadType_ReturnsThread()
    {
        // Arrange
        var thread = new TestAgentThread();

        // Act
        var result = thread.GetService(typeof(AgentThread));

        // Assert
        Assert.NotNull(result);
        Assert.Same(thread, result);
    }

    /// <summary>
    /// Verify that GetService returns null when requesting an unrelated type.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnrelatedType_ReturnsNull()
    {
        // Arrange
        var thread = new TestAgentThread();

        // Act
        var result = thread.GetService(typeof(string));

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
        var thread = new TestAgentThread();

        // Act
        var result = thread.GetService(typeof(TestAgentThread), "some-key");

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
        var thread = new TestAgentThread();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => thread.GetService(null!));
    }

    /// <summary>
    /// Verify that GetService generic method works correctly.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsCorrectType()
    {
        // Arrange
        var thread = new TestAgentThread();

        // Act
        var result = thread.GetService<TestAgentThread>();

        // Assert
        Assert.NotNull(result);
        Assert.Same(thread, result);
    }

    /// <summary>
    /// Verify that GetService generic method returns null for unrelated types.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsNullForUnrelatedType()
    {
        // Arrange
        var thread = new TestAgentThread();

        // Act
        var result = thread.GetService<string>();

        // Assert
        Assert.Null(result);
    }

    #endregion

    private sealed class TestAgentThread : AgentThread;
}
