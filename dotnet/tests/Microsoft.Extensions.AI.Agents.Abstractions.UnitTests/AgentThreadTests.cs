// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

#pragma warning disable CA1861 // Avoid constant arrays as arguments

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

/// <summary>
/// Tests for <see cref="AgentThread"/>
/// </summary>
public class AgentThreadTests
{
    [Fact]
    public async Task SerializeAsync_ReturnsDefaultJsonElementAsync()
    {
        var thread = new TestAgentThread();
        var result = await thread.SerializeAsync();
        Assert.Equal(default, result);
    }

    [Fact]
    public void MessagesReceivedAsync_ReturnsCompletedTask()
    {
        var thread = new TestAgentThread();
        var messages = new List<ChatMessage> { new(ChatRole.User, "hello") };
        var result = thread.MessagesReceivedAsync(messages);
        Assert.True(result.IsCompleted);
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

    private sealed class TestAgentThread : AgentThread
    {
        protected internal override Task MessagesReceivedAsync(IEnumerable<ChatMessage> newMessages, CancellationToken cancellationToken = default)
            => base.MessagesReceivedAsync(newMessages, cancellationToken);

        public override Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => base.SerializeAsync(jsonSerializerOptions, cancellationToken);
    }
}
