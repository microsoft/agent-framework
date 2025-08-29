// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

public class AgentThreadTests
{
    #region Constructor and Property Tests

    [Fact]
    public void ConstructorSetsDefaults()
    {
        // Arrange & Act
        var thread = new AgentThread();

        // Assert
        Assert.Null(thread.ConversationId);
        Assert.Null(thread.MessageStore);
    }

    [Fact]
    public void SetConversationIdRoundtrips()
    {
        // Arrange
        var thread = new AgentThread();
        var conversationid = "test-thread-id";

        // Act
        thread.ConversationId = conversationid;

        // Assert
        Assert.Equal(conversationid, thread.ConversationId);
        Assert.Null(thread.MessageStore);
    }

    [Fact]
    public void SetChatMessageStoreRoundtrips()
    {
        // Arrange
        var thread = new AgentThread();
        var messageStore = new InMemoryChatMessageStore();

        // Act
        thread.MessageStore = messageStore;

        // Assert
        Assert.Same(messageStore, thread.MessageStore);
        Assert.Null(thread.ConversationId);
    }

    [Fact]
    public void SetConversationIdThrowsWhenMessageStoreIsSet()
    {
        // Arrange
        var thread = new AgentThread
        {
            MessageStore = new InMemoryChatMessageStore()
        };

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => thread.ConversationId = "new-thread-id");
        Assert.Equal("Only the ConversationId or MessageStore may be set, but not both and switching from one to another is not supported.", exception.Message);
        Assert.NotNull(thread.MessageStore);
    }

    [Fact]
    public void SetChatMessageStoreThrowsWhenConversationIdIsSet()
    {
        // Arrange
        var thread = new AgentThread
        {
            ConversationId = "existing-thread-id"
        };
        var store = new InMemoryChatMessageStore();

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => thread.MessageStore = store);
        Assert.Equal("Only the ConversationId or MessageStore may be set, but not both and switching from one to another is not supported.", exception.Message);
        Assert.NotNull(thread.ConversationId);
    }

    #endregion Constructor and Property Tests

    #region GetMessagesAsync Tests

    [Fact]
    public async Task GetMessagesAsyncReturnsEmptyListWhenNoStoreAsync()
    {
        // Arrange
        var thread = new AgentThread();

        // Act
        var messages = await thread.GetMessagesAsync(CancellationToken.None).ToListAsync();

        // Assert
        Assert.Empty(messages);
    }

    [Fact]
    public async Task GetMessagesAsyncReturnsEmptyListWhenAgentServiceIdAsync()
    {
        // Arrange
        var thread = new AgentThread() { ConversationId = "thread-123" };

        // Act
        var messages = await thread.GetMessagesAsync(CancellationToken.None).ToListAsync();

        // Assert
        Assert.Empty(messages);
    }

    [Fact]
    public async Task GetMessagesAsyncReturnsMessagesFromStoreAsync()
    {
        // Arrange
        var store = new InMemoryChatMessageStore
        {
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi there!")
        };
        var thread = new AgentThread() { MessageStore = store };

        // Act
        var messages = await thread.GetMessagesAsync(CancellationToken.None).ToListAsync();

        // Assert
        Assert.Equal(2, messages.Count);
        Assert.Equal("Hello", messages[0].Text);
        Assert.Equal("Hi there!", messages[1].Text);
    }

    #endregion GetMessagesAsync Tests

    #region OnNewMessagesAsync Tests

    [Fact]
    public async Task OnNewMessagesAsyncDoesNothingWhenAgentServiceIdAsync()
    {
        // Arrange
        var thread = new AgentThread() { ConversationId = "thread-123" };
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };

        // Act
        await thread.OnNewMessagesAsync(messages, CancellationToken.None);
        Assert.Equal("thread-123", thread.ConversationId);
        Assert.Null(thread.MessageStore);
    }

    [Fact]
    public async Task OnNewMessagesAsyncAddsMessagesToStoreAsync()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var thread = new AgentThread() { MessageStore = store };
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };

        // Act
        await thread.OnNewMessagesAsync(messages, CancellationToken.None);

        // Assert
        Assert.Equal(2, store.Count);
        Assert.Equal("Hello", store[0].Text);
        Assert.Equal("Hi there!", store[1].Text);
    }

    #endregion OnNewMessagesAsync Tests

    #region Deserialize Tests

    [Fact]
    public async Task VerifyDeserializeWithMessagesAsync()
    {
        // Arrange
        var chatMessageStore = new InMemoryChatMessageStore();
        var json = JsonSerializer.Deserialize<JsonElement>("""
            {
                "storeState": { "messages": [{"authorName": "testAuthor"}] }
            }
            """);
        var thread = new AgentThread() { MessageStore = chatMessageStore };

        // Act.
        await thread.DeserializeAsync(json);

        // Assert
        Assert.Null(thread.ConversationId);

        Assert.Single(chatMessageStore);
        Assert.Equal("testAuthor", chatMessageStore[0].AuthorName);
    }

    [Fact]
    public async Task VerifyDeserializeWithIdAsync()
    {
        // Arrange
        var json = JsonSerializer.Deserialize<JsonElement>("""
            {
                "conversationId": "TestConvId"
            }
            """);
        var thread = new AgentThread();

        // Act
        await thread.DeserializeAsync(json);

        // Assert
        Assert.Equal("TestConvId", thread.ConversationId);
        Assert.Null(thread.MessageStore);
    }

    [Fact]
    public async Task DeserializeWithInvalidJsonThrowsAsync()
    {
        // Arrange
        var invalidJson = JsonSerializer.Deserialize<JsonElement>("[42]");
        var thread = new AgentThread();

        // Act & Assert
        await Assert.ThrowsAsync<JsonException>(() => thread.DeserializeAsync(invalidJson));
    }

    #endregion Deserialize Tests

    #region Serialize Tests

    /// <summary>
    /// Verify thread serialization to JSON when the thread has an id.
    /// </summary>
    [Fact]
    public async Task VerifyThreadSerializationWithIdAsync()
    {
        // Arrange
        var thread = new AgentThread() { ConversationId = "TestConvId" };

        // Act
        var json = await thread.SerializeAsync();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.True(json.TryGetProperty("conversationId", out var idProperty));
        Assert.Equal("TestConvId", idProperty.GetString());

        Assert.False(json.TryGetProperty("storeState", out var storeStateProperty));
    }

    /// <summary>
    /// Verify thread serialization to JSON when the thread has messages.
    /// </summary>
    [Fact]
    public async Task VerifyThreadSerializationWithMessagesAsync()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        store.Add(new ChatMessage(ChatRole.User, "TestContent") { AuthorName = "TestAuthor" });
        var thread = new AgentThread() { MessageStore = store };

        // Act
        var json = await thread.SerializeAsync();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.False(json.TryGetProperty("conversationId", out var idProperty));

        Assert.True(json.TryGetProperty("storeState", out var storeStateProperty));
        Assert.Equal(JsonValueKind.Object, storeStateProperty.ValueKind);

        Assert.True(storeStateProperty.TryGetProperty("messages", out var messagesProperty));
        Assert.Equal(JsonValueKind.Array, messagesProperty.ValueKind);
        Assert.Single(messagesProperty.EnumerateArray());

        var message = messagesProperty.EnumerateArray().First();
        Assert.Equal("TestAuthor", message.GetProperty("authorName").GetString());
        Assert.True(message.TryGetProperty("contents", out var contentsProperty));
        Assert.Equal(JsonValueKind.Array, contentsProperty.ValueKind);
        Assert.Single(contentsProperty.EnumerateArray());

        var textContent = contentsProperty.EnumerateArray().First();
        Assert.Equal("TestContent", textContent.GetProperty("text").GetString());
    }

    /// <summary>
    /// Verify thread serialization to JSON with custom options.
    /// </summary>
    [Fact]
    public async Task VerifyThreadSerializationWithCustomOptionsAsync()
    {
        // Arrange
        var thread = new AgentThread();
        JsonSerializerOptions options = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);

        var storeStateElement = JsonSerializer.SerializeToElement(new { Key = "TestValue" });

        var messageStoreMock = new Mock<IChatMessageStore>();
        messageStoreMock
            .Setup(m => m.SerializeStateAsync(options, It.IsAny<CancellationToken>()))
            .ReturnsAsync(storeStateElement);
        thread.MessageStore = messageStoreMock.Object;

        // Act
        var json = await thread.SerializeAsync(options);

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.False(json.TryGetProperty("conversationId", out var idProperty));

        Assert.True(json.TryGetProperty("storeState", out var storeStateProperty));
        Assert.Equal(JsonValueKind.Object, storeStateProperty.ValueKind);

        Assert.True(storeStateProperty.TryGetProperty("Key", out var keyProperty));
        Assert.Equal("TestValue", keyProperty.GetString());

        messageStoreMock.Verify(m => m.SerializeStateAsync(options, It.IsAny<CancellationToken>()), Times.Once);
    }

    #endregion Serialize Tests
}
