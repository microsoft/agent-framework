// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for <see cref="InMemoryAgentSession"/>.
/// </summary>
public class InMemoryAgentSessionTests
{
    #region Constructor and Property Tests

    [Fact]
    public void Constructor_SetsDefaultChatHistoryProvider()
    {
        // Arrange & Act
        var session = new TestInMemoryAgentSession();

        // Assert
        Assert.NotNull(session.ChatHistoryProvider);
        Assert.Empty(session.ChatHistoryProvider.GetMessages(session));
    }

    [Fact]
    public void Constructor_WithChatHistoryProvider_SetsProperty()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var session = new TestInMemoryAgentSession(provider);
        provider.SetMessages(session, [new(ChatRole.User, "Hello")]);

        // Act & Assert
        Assert.Same(provider, session.ChatHistoryProvider);
        var messages = session.ChatHistoryProvider.GetMessages(session);
        Assert.Single(messages);
        Assert.Equal("Hello", messages[0].Text);
    }

    [Fact]
    public void Constructor_WithMessages_SetsProperty()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hi") };

        // Act
        var session = new TestInMemoryAgentSession(messages);

        // Assert
        Assert.NotNull(session.ChatHistoryProvider);
        Assert.Single(session.ChatHistoryProvider.GetMessages(session));
        Assert.Equal("Hi", session.ChatHistoryProvider.GetMessages(session)[0].Text);
    }

    [Fact]
    public void Constructor_WithSerializedState_SetsProperty()
    {
        // Arrange - create a session with a StateBag containing chat history
        var originalSession = new TestInMemoryAgentSession([new(ChatRole.User, "TestMsg")]);
        var json = originalSession.Serialize();

        // Act
        var session = new TestInMemoryAgentSession(json);

        // Assert
        Assert.NotNull(session.ChatHistoryProvider);
        var messages = session.ChatHistoryProvider.GetMessages(session);
        Assert.Single(messages);
        Assert.Equal("TestMsg", messages[0].Text);
    }

    [Fact]
    public void Constructor_WithInvalidJson_ThrowsArgumentException()
    {
        // Arrange
        var invalidJson = JsonSerializer.SerializeToElement(42, TestJsonSerializerContext.Default.Int32);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new TestInMemoryAgentSession(invalidJson));
    }

    #endregion

    #region SerializeAsync Tests

    [Fact]
    public void Serialize_ReturnsCorrectJson_WhenMessagesExist()
    {
        // Arrange
        var session = new TestInMemoryAgentSession([new(ChatRole.User, "TestContent")]);

        // Act
        var json = session.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("stateBag", out var stateBagProperty));
        Assert.Equal(JsonValueKind.Object, stateBagProperty.ValueKind);
        Assert.True(stateBagProperty.TryGetProperty("InMemoryChatHistoryProvider.State", out var providerStateProperty));
        Assert.Equal(JsonValueKind.Object, providerStateProperty.ValueKind);
        Assert.True(providerStateProperty.TryGetProperty("messages", out var messagesProperty));
        Assert.Equal(JsonValueKind.Array, messagesProperty.ValueKind);
        var messagesList = messagesProperty.EnumerateArray().ToList();
        Assert.Single(messagesList);
    }

    [Fact]
    public void Serialize_ReturnsEmptyStateBag_WhenNoMessages()
    {
        // Arrange
        var session = new TestInMemoryAgentSession();

        // Act
        var json = session.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("stateBag", out var providerStateProperty));
        Assert.Equal(JsonValueKind.Object, providerStateProperty.ValueKind);
        Assert.False(providerStateProperty.EnumerateObject().Any());
    }

    #endregion

    #region GetService Tests

    [Fact]
    public void GetService_RequestingChatHistoryProvider_ReturnsChatHistoryProvider()
    {
        // Arrange
        var session = new TestInMemoryAgentSession();

        // Act & Assert
        Assert.NotNull(session.GetService(typeof(ChatHistoryProvider)));
        Assert.Same(session.ChatHistoryProvider, session.GetService(typeof(ChatHistoryProvider)));
        Assert.Same(session.ChatHistoryProvider, session.GetService(typeof(InMemoryChatHistoryProvider)));
    }

    #endregion

    // Sealed test subclass to expose protected members for testing
    private sealed class TestInMemoryAgentSession : InMemoryAgentSession
    {
        public TestInMemoryAgentSession() { }
        public TestInMemoryAgentSession(InMemoryChatHistoryProvider? provider) : base(provider) { }
        public TestInMemoryAgentSession(IEnumerable<ChatMessage> messages) : base(messages) { }
        public TestInMemoryAgentSession(JsonElement serializedSessionState) : base(serializedSessionState) { }
    }
}
