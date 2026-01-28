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
        Assert.NotNull(session.GetChatHistoryProvider());
        Assert.Empty(session.GetChatHistoryProvider());
    }

    [Fact]
    public void Constructor_WithChatHistoryProvider_SetsProperty()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = [new(ChatRole.User, "Hello")];

        // Act
        var session = new TestInMemoryAgentSession(provider);

        // Assert
        Assert.Same(provider, session.GetChatHistoryProvider());
        Assert.Single(session.GetChatHistoryProvider());
        Assert.Equal("Hello", session.GetChatHistoryProvider()[0].Text);
    }

    [Fact]
    public void Constructor_WithMessages_SetsProperty()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hi") };

        // Act
        var session = new TestInMemoryAgentSession(messages);

        // Assert
        Assert.NotNull(session.GetChatHistoryProvider());
        Assert.Single(session.GetChatHistoryProvider());
        Assert.Equal("Hi", session.GetChatHistoryProvider()[0].Text);
    }

    [Fact]
    public void Constructor_WithSerializedState_SetsProperty()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = [new(ChatRole.User, "TestMsg")];
        var providerState = provider.Serialize();
        var sessionStateWrapper = new InMemoryAgentSession.InMemoryAgentSessionState { ChatHistoryProviderState = providerState };
        var json = JsonSerializer.SerializeToElement(sessionStateWrapper, TestJsonSerializerContext.Default.InMemoryAgentSessionState);

        // Act
        var session = new TestInMemoryAgentSession(json);

        // Assert
        Assert.NotNull(session.GetChatHistoryProvider());
        Assert.Single(session.GetChatHistoryProvider());
        Assert.Equal("TestMsg", session.GetChatHistoryProvider()[0].Text);
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
        Assert.True(json.TryGetProperty("chatHistoryProviderState", out var providerStateProperty));
        Assert.Equal(JsonValueKind.Object, providerStateProperty.ValueKind);
        Assert.True(providerStateProperty.TryGetProperty("messages", out var messagesProperty));
        Assert.Equal(JsonValueKind.Array, messagesProperty.ValueKind);
        var messagesList = messagesProperty.EnumerateArray().ToList();
        Assert.Single(messagesList);
    }

    [Fact]
    public void Serialize_ReturnsEmptyMessages_WhenNoMessages()
    {
        // Arrange
        var session = new TestInMemoryAgentSession();

        // Act
        var json = session.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("chatHistoryProviderState", out var providerStateProperty));
        Assert.Equal(JsonValueKind.Object, providerStateProperty.ValueKind);
        Assert.True(providerStateProperty.TryGetProperty("messages", out var messagesProperty));
        Assert.Equal(JsonValueKind.Array, messagesProperty.ValueKind);
        Assert.Empty(messagesProperty.EnumerateArray());
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
        Assert.Same(session.GetChatHistoryProvider(), session.GetService(typeof(ChatHistoryProvider)));
        Assert.Same(session.GetChatHistoryProvider(), session.GetService(typeof(InMemoryChatHistoryProvider)));
    }

    #endregion

    // Sealed test subclass to expose protected members for testing
    private sealed class TestInMemoryAgentSession : InMemoryAgentSession
    {
        public TestInMemoryAgentSession() { }
        public TestInMemoryAgentSession(InMemoryChatHistoryProvider? provider) : base(provider) { }
        public TestInMemoryAgentSession(IEnumerable<ChatMessage> messages) : base(messages) { }
        public TestInMemoryAgentSession(JsonElement serializedSessionState) : base(serializedSessionState) { }
        public InMemoryChatHistoryProvider GetChatHistoryProvider() => this.ChatHistoryProvider;
    }
}
