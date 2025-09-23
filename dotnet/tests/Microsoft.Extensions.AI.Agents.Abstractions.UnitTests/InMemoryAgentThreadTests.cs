// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

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
        var store = new InMemoryChatMessageStore();
        store.Add(new ChatMessage(ChatRole.User, "Hello"));

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
    public async Task Constructor_WithSerializedState_SetsPropertyAsync()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        store.Add(new ChatMessage(ChatRole.User, "TestMsg"));
        var storeState = await store.SerializeStateAsync();
        var json = JsonSerializer.SerializeToElement(new { storeState });

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
        var invalidJson = JsonSerializer.SerializeToElement(42);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new TestInMemoryAgentThread(invalidJson));
    }

    #endregion

    #region SerializeAsync Tests

    [Fact]
    public async Task SerializeAsync_ReturnsCorrectJson_WhenMessagesExistAsync()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        store.Add(new ChatMessage(ChatRole.User, "TestContent"));
        var thread = new TestInMemoryAgentThread(store);

        // Act
        var json = await thread.SerializeAsync();

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
    public async Task SerializeAsync_ReturnsEmptyMessages_WhenNoMessagesAsync()
    {
        // Arrange
        var thread = new TestInMemoryAgentThread();

        // Act
        var json = await thread.SerializeAsync();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("storeState", out var storeStateProperty));
        Assert.Equal(JsonValueKind.Object, storeStateProperty.ValueKind);
        Assert.True(storeStateProperty.TryGetProperty("messages", out var messagesProperty));
        Assert.Equal(JsonValueKind.Array, messagesProperty.ValueKind);
        Assert.Empty(messagesProperty.EnumerateArray());
    }

    #endregion

    // Sealed test subclass to expose protected members for testing
    private sealed class TestInMemoryAgentThread : InMemoryAgentThread
    {
        public TestInMemoryAgentThread() : base() { }
        public TestInMemoryAgentThread(InMemoryChatMessageStore? store) : base(store) { }
        public TestInMemoryAgentThread(IEnumerable<ChatMessage> messages) : base(messages) { }
        public TestInMemoryAgentThread(JsonElement serializedThreadState) : base(serializedThreadState) { }
        public InMemoryChatMessageStore GetMessageStore() => this.MessageStore;
        public override Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) => base.SerializeAsync(jsonSerializerOptions, cancellationToken);
    }
}
