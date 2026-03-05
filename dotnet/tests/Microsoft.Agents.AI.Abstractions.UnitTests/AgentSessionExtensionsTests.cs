// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Tests for <see cref="AgentSessionExtensions"/>.
/// </summary>
public class AgentSessionExtensionsTests
{
    #region TryGetInMemoryChatHistory Tests

    [Fact]
    public void TryGetInMemoryChatHistory_WithNullSession_ThrowsArgumentNullException()
    {
        // Arrange
        AgentSession session = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => session.TryGetInMemoryChatHistory(out _));
    }

    [Fact]
    public void TryGetInMemoryChatHistory_WhenStateExists_ReturnsTrueAndMessages()
    {
        // Arrange
        var session = new Mock<AgentSession>().Object;
        var expectedMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };

        session.StateBag.SetValue(
            nameof(InMemoryChatHistoryProvider),
            new InMemoryChatHistoryProvider.State { Messages = expectedMessages });

        // Act
        var result = session.TryGetInMemoryChatHistory(out var messages);

        // Assert
        Assert.True(result);
        Assert.NotNull(messages);
        Assert.Same(expectedMessages, messages);
    }

    [Fact]
    public void TryGetInMemoryChatHistory_WhenStateDoesNotExist_ReturnsFalse()
    {
        // Arrange
        var session = new Mock<AgentSession>().Object;

        // Act
        var result = session.TryGetInMemoryChatHistory(out var messages);

        // Assert
        Assert.False(result);
        Assert.Null(messages);
    }

    [Fact]
    public void TryGetInMemoryChatHistory_WithCustomStateKey_UsesCustomKey()
    {
        // Arrange
        var session = new Mock<AgentSession>().Object;
        const string CustomKey = "custom-history-key";
        var expectedMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        session.StateBag.SetValue(
            CustomKey,
            new InMemoryChatHistoryProvider.State { Messages = expectedMessages });

        // Act
        var result = session.TryGetInMemoryChatHistory(out var messages, stateKey: CustomKey);

        // Assert
        Assert.True(result);
        Assert.NotNull(messages);
        Assert.Same(expectedMessages, messages);
    }

    [Fact]
    public void TryGetInMemoryChatHistory_WithCustomStateKey_DoesNotFindDefaultKey()
    {
        // Arrange
        var session = new Mock<AgentSession>().Object;
        var expectedMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        session.StateBag.SetValue(
            nameof(InMemoryChatHistoryProvider),
            new InMemoryChatHistoryProvider.State { Messages = expectedMessages });

        // Act
        var result = session.TryGetInMemoryChatHistory(out var messages, stateKey: "other-key");

        // Assert
        Assert.False(result);
        Assert.Null(messages);
    }

    [Fact]
    public void TryGetInMemoryChatHistory_WhenStateExistsWithNullMessages_ReturnsFalse()
    {
        // Arrange
        var session = new Mock<AgentSession>().Object;
        session.StateBag.SetValue(
            nameof(InMemoryChatHistoryProvider),
            new InMemoryChatHistoryProvider.State { Messages = null! });

        // Act
        var result = session.TryGetInMemoryChatHistory(out var messages);

        // Assert
        Assert.False(result);
        Assert.Null(messages);
    }

    #endregion

    #region SetInMemoryChatHistory Tests

    [Fact]
    public void SetInMemoryChatHistory_WithNullSession_ThrowsArgumentNullException()
    {
        // Arrange
        AgentSession session = null!;
        var messages = new List<ChatMessage>();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => session.SetInMemoryChatHistory(messages));
    }

    [Fact]
    public void SetInMemoryChatHistory_WhenNoExistingState_CreatesNewState()
    {
        // Arrange
        var session = new Mock<AgentSession>().Object;
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi!")
        };

        // Act
        session.SetInMemoryChatHistory(messages);

        // Assert
        var result = session.TryGetInMemoryChatHistory(out var retrievedMessages);
        Assert.True(result);
        Assert.Same(messages, retrievedMessages);
    }

    [Fact]
    public void SetInMemoryChatHistory_WhenExistingState_ReplacesMessages()
    {
        // Arrange
        var session = new Mock<AgentSession>().Object;
        var originalMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Original")
        };
        var newMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "New message"),
            new(ChatRole.Assistant, "New response")
        };

        session.SetInMemoryChatHistory(originalMessages);

        // Act
        session.SetInMemoryChatHistory(newMessages);

        // Assert
        var result = session.TryGetInMemoryChatHistory(out var retrievedMessages);
        Assert.True(result);
        Assert.Same(newMessages, retrievedMessages);
    }

    [Fact]
    public void SetInMemoryChatHistory_WithCustomStateKey_UsesCustomKey()
    {
        // Arrange
        var session = new Mock<AgentSession>().Object;
        const string CustomKey = "custom-history-key";
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test")
        };

        // Act
        session.SetInMemoryChatHistory(messages, stateKey: CustomKey);

        // Assert
        var result = session.TryGetInMemoryChatHistory(out var retrievedMessages, stateKey: CustomKey);
        Assert.True(result);
        Assert.Same(messages, retrievedMessages);

        // Verify default key is not set
        var defaultResult = session.TryGetInMemoryChatHistory(out _);
        Assert.False(defaultResult);
    }

    [Fact]
    public void SetInMemoryChatHistory_WithEmptyList_SetsEmptyList()
    {
        // Arrange
        var session = new Mock<AgentSession>().Object;
        var messages = new List<ChatMessage>();

        // Act
        session.SetInMemoryChatHistory(messages);

        // Assert
        var result = session.TryGetInMemoryChatHistory(out var retrievedMessages);
        Assert.True(result);
        Assert.NotNull(retrievedMessages);
        Assert.Empty(retrievedMessages);
    }

    #endregion
}
