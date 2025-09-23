// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Moq;

#pragma warning disable CA1861 // Avoid constant arrays as arguments

namespace Microsoft.Extensions.AI.Agents.UnitTests.ChatCompletion;

public class ChatClientAgentThreadTests
{
    #region Constructor and Property Tests

    [Fact]
    public void ConstructorSetsDefaults()
    {
        // Arrange & Act
        var thread = new ChatClientAgentThread();

        // Assert
        Assert.Null(thread.ConversationId);
        Assert.Null(thread.MessageStore);
    }

    [Fact]
    public void SetConversationIdRoundtrips()
    {
        // Arrange
        var thread = new ChatClientAgentThread();
        const string ConversationId = "test-thread-id";

        // Act
        thread.ConversationId = ConversationId;

        // Assert
        Assert.Equal(ConversationId, thread.ConversationId);
        Assert.Null(thread.MessageStore);
    }

    [Fact]
    public void SetChatMessageStoreRoundtrips()
    {
        // Arrange
        var thread = new ChatClientAgentThread();
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
        var thread = new ChatClientAgentThread
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
        var thread = new ChatClientAgentThread
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

    #region OnNewMessagesAsync Tests

    [Fact]
    public async Task OnNewMessagesAsyncDoesNothingWhenAgentServiceIdAsync()
    {
        // Arrange
        var thread = new ChatClientAgentThread { ConversationId = "thread-123" };
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var agent = new MessageSendingAgent();

        // Act
        await agent.SendMessagesAsync(thread, messages, CancellationToken.None);
        Assert.Equal("thread-123", thread.ConversationId);
        Assert.Null(thread.MessageStore);
    }

    [Fact]
    public async Task OnNewMessagesAsyncAddsMessagesToStoreAsync()
    {
        // Arrange
        var store = new InMemoryChatMessageStore();
        var thread = new ChatClientAgentThread { MessageStore = store };
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var agent = new MessageSendingAgent();

        // Act
        await agent.SendMessagesAsync(thread, messages, CancellationToken.None);

        // Assert
        Assert.Equal(2, store.Count);
        Assert.Equal("Hello", store[0].Text);
        Assert.Equal("Hi there!", store[1].Text);
    }

    #endregion OnNewMessagesAsync Tests

    #region Deserialize Tests

    [Fact]
    public async Task VerifyDeserializeConstructorWithMessagesAsync()
    {
        // Arrange
        var json = JsonSerializer.Deserialize("""
            {
                "storeState": { "messages": [{"authorName": "testAuthor"}] }
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act.
        var thread = new ChatClientAgentThread(json);

        // Assert
        Assert.Null(thread.ConversationId);

        var messageStore = thread.MessageStore as InMemoryChatMessageStore;
        Assert.NotNull(messageStore);
        Assert.Single(messageStore);
        Assert.Equal("testAuthor", messageStore[0].AuthorName);
    }

    [Fact]
    public async Task VerifyDeserializeConstructorWithIdAsync()
    {
        // Arrange
        var json = JsonSerializer.Deserialize("""
            {
                "conversationId": "TestConvId"
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act
        var thread = new ChatClientAgentThread(json);

        // Assert
        Assert.Equal("TestConvId", thread.ConversationId);
        Assert.Null(thread.MessageStore);
    }

    [Fact]
    public async Task VerifyDeserializeConstructorWithAIContextProviderAsync()
    {
        // Arrange
        var json = JsonSerializer.Deserialize("""
            {
                "conversationId": "TestConvId",
                "aiContextProviderState": ["CP1"]
            }
            """, TestJsonSerializerContext.Default.JsonElement);
        Mock<AIContextProvider> mockProvider = new();

        // Act
        var thread = new ChatClientAgentThread(json, aiContextProviderFactory: (_, _) => mockProvider.Object);

        // Assert
        Assert.Null(thread.MessageStore);
        Assert.Same(thread.AIContextProvider, mockProvider.Object);
    }

    [Fact]
    public async Task DeserializeContructorWithInvalidJsonThrowsAsync()
    {
        // Arrange
        var invalidJson = JsonSerializer.Deserialize("[42]", TestJsonSerializerContext.Default.JsonElement);
        var thread = new ChatClientAgentThread();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new ChatClientAgentThread(invalidJson));
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
        var thread = new ChatClientAgentThread { ConversationId = "TestConvId" };

        // Act
        var json = await thread.SerializeAsync();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.True(json.TryGetProperty("conversationId", out var idProperty));
        Assert.Equal("TestConvId", idProperty.GetString());

        Assert.False(json.TryGetProperty("storeState", out _));
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
        var thread = new ChatClientAgentThread { MessageStore = store };

        // Act
        var json = await thread.SerializeAsync();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.False(json.TryGetProperty("conversationId", out _));

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

    [Fact]
    public async Task VerifyThreadSerializationWithWithAIContextProviderAsync()
    {
        // Arrange
        Mock<AIContextProvider> mockProvider = new();
        var providerStateElement = JsonSerializer.SerializeToElement(new[] { "CP1" }, TestJsonSerializerContext.Default.StringArray);
        mockProvider
            .Setup(m => m.SerializeAsync(It.IsAny<JsonSerializerOptions?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(providerStateElement);

        var thread = new ChatClientAgentThread();
        thread.AIContextProvider = mockProvider.Object;

        // Act
        var json = await thread.SerializeAsync();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("aiContextProviderState", out var providerStateProperty));
        Assert.Equal(JsonValueKind.Array, providerStateProperty.ValueKind);
        Assert.Single(providerStateProperty.EnumerateArray());
        Assert.Equal("CP1", providerStateProperty.EnumerateArray().First().GetString());
        mockProvider.Verify(m => m.SerializeAsync(It.IsAny<JsonSerializerOptions?>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verify thread serialization to JSON with custom options.
    /// </summary>
    [Fact]
    public async Task VerifyThreadSerializationWithCustomOptionsAsync()
    {
        // Arrange
        var thread = new ChatClientAgentThread();
        JsonSerializerOptions options = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);

        var storeStateElement = JsonSerializer.SerializeToElement(
            new Dictionary<string, object> { ["Key"] = "TestValue" },
            TestJsonSerializerContext.Default.DictionaryStringObject);

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

    private sealed class MessageSendingAgent : AIAgent
    {
        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            => throw new NotImplementedException();

        public override AgentThread GetNewThread()
            => throw new NotImplementedException();

        public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        public Task SendMessagesAsync(AgentThread thread, IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
            => NotifyThreadOfNewMessagesAsync(thread, messages, cancellationToken);
    }
}
