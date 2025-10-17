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
    public void Constructor_SetsDefaultMessageStore()
    {
        // Arrange & Act
        var thread = new TestInMemoryAgentThread();

        // Assert
        Assert.NotNull(thread.GetMessageStore());
        Assert.Empty(thread.GetMessageStore());
    }

    [Fact]
    public void Constructor_WithMessageStore_SetsProperty()
    {
        // Arrange
        InMemoryChatMessageStore store = [new(ChatRole.User, "Hello")];

        // Act
        var thread = new TestInMemoryAgentThread(store);

        // Assert
        Assert.Same(store, thread.GetMessageStore());
        Assert.Single(thread.GetMessageStore());
        Assert.Equal("Hello", thread.GetMessageStore()[0].Text);
    }

    [Fact]
    public void Constructor_WithMessages_SetsProperty()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hi") };

        // Act
        var thread = new TestInMemoryAgentThread(messages);

        // Assert
        Assert.NotNull(thread.GetMessageStore());
        Assert.Single(thread.GetMessageStore());
        Assert.Equal("Hi", thread.GetMessageStore()[0].Text);
    }

    [Fact]
    public void Constructor_WithSerializedState_SetsProperty()
    {
        // Arrange
        InMemoryChatMessageStore store = [new(ChatRole.User, "TestMsg")];
        var storeState = store.Serialize();
        var threadStateWrapper = new InMemoryAgentThread.InMemoryAgentThreadState { StoreState = storeState };
        var json = JsonSerializer.SerializeToElement(threadStateWrapper, TestJsonSerializerContext.Default.InMemoryAgentThreadState);

        // Act
        var thread = new TestInMemoryAgentThread(json);

        // Assert
        Assert.NotNull(thread.GetMessageStore());
        Assert.Single(thread.GetMessageStore());
        Assert.Equal("TestMsg", thread.GetMessageStore()[0].Text);
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
        Assert.True(json.TryGetProperty("storeState", out var storeStateProperty));
        Assert.Equal(JsonValueKind.Object, storeStateProperty.ValueKind);
        Assert.True(storeStateProperty.TryGetProperty("messages", out var messagesProperty));
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
        Assert.True(json.TryGetProperty("storeState", out var storeStateProperty));
        Assert.Equal(JsonValueKind.Object, storeStateProperty.ValueKind);
        Assert.True(storeStateProperty.TryGetProperty("messages", out var messagesProperty));
        Assert.Equal(JsonValueKind.Array, messagesProperty.ValueKind);
        Assert.Empty(messagesProperty.EnumerateArray());
    }

    #endregion

    #region GetService Tests

    [Fact]
    public void GetService_RequestingChatMessageStore_ReturnsChatMessageStore()
    {
        // Arrange
        var thread = new TestInMemoryAgentThread();

        // Act & Assert
        Assert.NotNull(thread.GetService(typeof(ChatMessageStore)));
        Assert.Same(thread.GetMessageStore(), thread.GetService(typeof(ChatMessageStore)));
        Assert.Same(thread.GetMessageStore(), thread.GetService(typeof(InMemoryChatMessageStore)));
    }

    #endregion

    // Sealed test subclass to expose protected members for testing
    private sealed class TestInMemoryAgentThread : InMemoryAgentThread
    {
        public TestInMemoryAgentThread() { }
        public TestInMemoryAgentThread(InMemoryChatMessageStore? store) : base(store) { }
        public TestInMemoryAgentThread(IEnumerable<ChatMessage> messages) : base(messages) { }
        public TestInMemoryAgentThread(JsonElement serializedThreadState) : base(serializedThreadState) { }
        public InMemoryChatMessageStore GetMessageStore() => this.MessageStore;
    }
}
