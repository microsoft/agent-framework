// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

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
        Assert.Null(thread.Id);
        Assert.Null(thread.ChatMessageStore);
    }

    [Fact]
    public void IdConstructorSetsId()
    {
        // Arrange & Act
        var thread = new AgentThread("thread-123");

        // Assert
        Assert.Equal("thread-123", thread.Id);
        Assert.Null(thread.ChatMessageStore);
    }

    [Fact]
    public void ChatMessageStoreConstructorSetsStore()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();

        // Act
        var thread = new AgentThread(store);

        // Assert
        Assert.Null(thread.Id);
        Assert.Equal(store, thread.ChatMessageStore);
    }

    [Fact]
    public void SetIdResetsChatMessageStoreAndRoundtrips()
    {
        // Arrange
        var thread = new AgentThread();
        thread.ChatMessageStore = new InMemoryChatMessageStore();

        // Act
        thread.Id = "new-thread-id";

        // Assert
        Assert.Equal("new-thread-id", thread.Id);
        Assert.Null(thread.ChatMessageStore);
    }

    [Fact]
    public void SetChatMessageStoreResetsIdAndRoundtrips()
    {
        // Arrange
        var thread = new AgentThread();
        thread.Id = "existing-thread-id";
        var store = new InMemoryChatMessageStore();

        // Act
        thread.ChatMessageStore = store;

        // Assert
        Assert.Equal(store, thread.ChatMessageStore);
        Assert.Null(thread.Id);
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
        var thread = new AgentThread("thread-123");

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
        var thread = new AgentThread(store);

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
        var thread = new AgentThread("thread-123");
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };

        // Act
        await thread.OnNewMessagesAsync(messages, CancellationToken.None);
    }

    [Fact]
    public async Task OnNewMessagesAsyncAddsMessagesToStoreAsync()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var thread = new AgentThread(store);
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
        var thread = new AgentThread(chatMessageStore);

        // Act.
        await thread.DeserializeAsync(json);

        // Assert
        Assert.Null(thread.Id);

        Assert.Single(chatMessageStore);
        Assert.Equal("testAuthor", chatMessageStore[0].AuthorName);
    }

    [Fact]
    public async Task VerifyDeserializeWithIdAsync()
    {
        // Arrange
        var json = JsonSerializer.Deserialize<JsonElement>("""
            {
                "id": "TestConvId"
            }
            """);
        var thread = new AgentThread();

        // Act
        await thread.DeserializeAsync(json);

        // Assert
        Assert.Equal("TestConvId", thread.Id);
        Assert.Null(thread.ChatMessageStore);
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
        var thread = new AgentThread("TestConvId");

        // Act
        var json = await thread.SerializeAsync();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.True(json.TryGetProperty("id", out var idProperty));
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
        var thread = new AgentThread(store);

        // Act
        var json = await thread.SerializeAsync();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.False(json.TryGetProperty("id", out var idProperty));

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
        var thread = new AgentThread("TestConvId");
        JsonSerializerOptions options = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);

        // Act
        var json = await thread.SerializeAsync(options);

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.True(json.TryGetProperty("id", out var idProperty));
        Assert.Equal("TestConvId", idProperty.GetString());

        Assert.True(json.TryGetProperty("store_state", out var storeStateProperty));
        Assert.Equal(JsonValueKind.Null, storeStateProperty.ValueKind); // Should be null since no messages are stored.
    }

    #endregion Serialize Tests
}
