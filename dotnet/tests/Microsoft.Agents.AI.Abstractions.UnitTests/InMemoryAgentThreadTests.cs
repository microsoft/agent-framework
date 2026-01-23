// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for <see cref="InMemoryAgentThread"/>.
/// </summary>
public class InMemoryAgentThreadTests
{
    #region Constructor and Property Tests

    [Fact]
    public void Constructor_SetsDefaultChatHistoryProvider()
    {
        // Arrange & Act
        var thread = new TestInMemoryAgentThread();

        // Assert
        Assert.NotNull(thread.GetChatHistoryProvider());
        Assert.Empty(thread.GetChatHistoryProvider());
    }

    [Fact]
    public void Constructor_WithChatHistoryProvider_SetsProperty()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = [new(ChatRole.User, "Hello")];

        // Act
        var thread = new TestInMemoryAgentThread(provider);

        // Assert
        Assert.Same(provider, thread.GetChatHistoryProvider());
        Assert.Single(thread.GetChatHistoryProvider());
        Assert.Equal("Hello", thread.GetChatHistoryProvider()[0].Text);
    }

    [Fact]
    public void Constructor_WithMessages_SetsProperty()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hi") };

        // Act
        var thread = new TestInMemoryAgentThread(messages);

        // Assert
        Assert.NotNull(thread.GetChatHistoryProvider());
        Assert.Single(thread.GetChatHistoryProvider());
        Assert.Equal("Hi", thread.GetChatHistoryProvider()[0].Text);
    }

    [Fact]
    public void Constructor_WithSerializedState_SetsProperty()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = [new(ChatRole.User, "TestMsg")];
        var providerState = provider.Serialize();
        var threadStateWrapper = new InMemoryAgentThread.InMemoryAgentThreadState { ChatHistoryProviderState = providerState };
        var json = JsonSerializer.SerializeToElement(threadStateWrapper, TestJsonSerializerContext.Default.InMemoryAgentThreadState);

        // Act
        var thread = new TestInMemoryAgentThread(json);

        // Assert
        Assert.NotNull(thread.GetChatHistoryProvider());
        Assert.Single(thread.GetChatHistoryProvider());
        Assert.Equal("TestMsg", thread.GetChatHistoryProvider()[0].Text);
    }

    [Fact]
    public void Constructor_WithInvalidJson_ThrowsArgumentException()
    {
        // Arrange
        var invalidJson = JsonSerializer.SerializeToElement(42, TestJsonSerializerContext.Default.Int32);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new TestInMemoryAgentThread(invalidJson));
    }

    #endregion

    #region SerializeAsync Tests

    [Fact]
    public void Serialize_ReturnsCorrectJson_WhenMessagesExist()
    {
        // Arrange
        var thread = new TestInMemoryAgentThread([new(ChatRole.User, "TestContent")]);

        // Act
        var json = thread.Serialize();

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
        var thread = new TestInMemoryAgentThread();

        // Act
        var json = thread.Serialize();

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
        var thread = new TestInMemoryAgentThread();

        // Act & Assert
        Assert.NotNull(thread.GetService(typeof(ChatHistoryProvider)));
        Assert.Same(thread.GetChatHistoryProvider(), thread.GetService(typeof(ChatHistoryProvider)));
        Assert.Same(thread.GetChatHistoryProvider(), thread.GetService(typeof(InMemoryChatHistoryProvider)));
    }

    #endregion

    // Sealed test subclass to expose protected members for testing
    private sealed class TestInMemoryAgentThread : InMemoryAgentThread
    {
        public TestInMemoryAgentThread() { }
        public TestInMemoryAgentThread(InMemoryChatHistoryProvider? provider) : base(provider) { }
        public TestInMemoryAgentThread(IEnumerable<ChatMessage> messages) : base(messages) { }
        public TestInMemoryAgentThread(JsonElement serializedThreadState) : base(serializedThreadState) { }
        public InMemoryChatHistoryProvider GetChatHistoryProvider() => this.ChatHistoryProvider;
    }
}
