// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

#pragma warning disable CA1861 // Avoid constant arrays as arguments

namespace Microsoft.Agents.AI.UnitTests;

public class ChatClientAgentSessionTests
{
    #region Constructor and Property Tests

    [Fact]
    public void ConstructorSetsDefaults()
    {
        // Arrange & Act
        var session = new ChatClientAgentSession();

        // Assert
        Assert.Null(session.ConversationId);
        Assert.Null(session.ChatHistoryProvider);
    }

    [Fact]
    public void SetConversationIdRoundtrips()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        const string ConversationId = "test-session-id";

        // Act
        session.ConversationId = ConversationId;

        // Assert
        Assert.Equal(ConversationId, session.ConversationId);
        Assert.Null(session.ChatHistoryProvider);
    }

    [Fact]
    public void SetChatHistoryProviderRoundtrips()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var chatHistoryProvider = new InMemoryChatHistoryProvider();

        // Act
        session.ChatHistoryProvider = chatHistoryProvider;

        // Assert
        Assert.Same(chatHistoryProvider, session.ChatHistoryProvider);
        Assert.Null(session.ConversationId);
    }

    [Fact]
    public void SetConversationIdThrowsWhenChatHistoryProviderIsSet()
    {
        // Arrange
        var session = new ChatClientAgentSession
        {
            ChatHistoryProvider = new InMemoryChatHistoryProvider()
        };

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => session.ConversationId = "new-session-id");
        Assert.Equal("Only the ConversationId or ChatHistoryProvider may be set, but not both and switching from one to another is not supported.", exception.Message);
        Assert.NotNull(session.ChatHistoryProvider);
    }

    [Fact]
    public void SetChatHistoryProviderThrowsWhenConversationIdIsSet()
    {
        // Arrange
        var session = new ChatClientAgentSession
        {
            ConversationId = "existing-session-id"
        };
        var provider = new InMemoryChatHistoryProvider();

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => session.ChatHistoryProvider = provider);
        Assert.Equal("Only the ConversationId or ChatHistoryProvider may be set, but not both and switching from one to another is not supported.", exception.Message);
        Assert.NotNull(session.ConversationId);
    }

    #endregion Constructor and Property Tests

    #region Deserialize Tests

    [Fact]
    public async Task VerifyDeserializeWithMessagesAsync()
    {
        // Arrange
        var json = JsonSerializer.Deserialize("""
            {
                "chatHistoryProviderState": { "messages": [{"authorName": "testAuthor"}] }
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act.
        var session = await ChatClientAgentSession.DeserializeAsync(json);

        // Assert
        Assert.Null(session.ConversationId);

        var chatHistoryProvider = session.ChatHistoryProvider as InMemoryChatHistoryProvider;
        Assert.NotNull(chatHistoryProvider);
        Assert.Single(chatHistoryProvider);
        Assert.Equal("testAuthor", chatHistoryProvider[0].AuthorName);
    }

    [Fact]
    public async Task VerifyDeserializeWithIdAsync()
    {
        // Arrange
        var json = JsonSerializer.Deserialize("""
            {
                "conversationId": "TestConvId"
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act
        var session = await ChatClientAgentSession.DeserializeAsync(json);

        // Assert
        Assert.Equal("TestConvId", session.ConversationId);
        Assert.Null(session.ChatHistoryProvider);
    }

    [Fact]
    public async Task VerifyDeserializeWithAIContextProviderAsync()
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
        var session = await ChatClientAgentSession.DeserializeAsync(json, aiContextProviderFactory: (_, _, _) => new(mockProvider.Object));

        // Assert
        Assert.Null(session.ChatHistoryProvider);
        Assert.Same(session.AIContextProvider, mockProvider.Object);
    }

    [Fact]
    public async Task DeserializeWithInvalidJsonThrowsAsync()
    {
        // Arrange
        var invalidJson = JsonSerializer.Deserialize("[42]", TestJsonSerializerContext.Default.JsonElement);
        var session = new ChatClientAgentSession();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => ChatClientAgentSession.DeserializeAsync(invalidJson));
    }

    #endregion Deserialize Tests

    #region Serialize Tests

    /// <summary>
    /// Verify session serialization to JSON when the session has an id.
    /// </summary>
    [Fact]
    public void VerifySessionSerializationWithId()
    {
        // Arrange
        var session = new ChatClientAgentSession { ConversationId = "TestConvId" };

        // Act
        var json = session.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.True(json.TryGetProperty("conversationId", out var idProperty));
        Assert.Equal("TestConvId", idProperty.GetString());

        Assert.False(json.TryGetProperty("chatHistoryProviderState", out _));
    }

    /// <summary>
    /// Verify session serialization to JSON when the session has messages.
    /// </summary>
    [Fact]
    public void VerifySessionSerializationWithMessages()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = [new(ChatRole.User, "TestContent") { AuthorName = "TestAuthor" }];
        var session = new ChatClientAgentSession { ChatHistoryProvider = provider };

        // Act
        var json = session.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.False(json.TryGetProperty("conversationId", out _));

        Assert.True(json.TryGetProperty("chatHistoryProviderState", out var chatHistoryProviderStateProperty));
        Assert.Equal(JsonValueKind.Object, chatHistoryProviderStateProperty.ValueKind);

        Assert.True(chatHistoryProviderStateProperty.TryGetProperty("messages", out var messagesProperty));
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
    public void VerifySessionSerializationWithWithAIContextProvider()
    {
        // Arrange
        Mock<AIContextProvider> mockProvider = new();
        mockProvider
            .Setup(m => m.Serialize(It.IsAny<JsonSerializerOptions?>()))
            .Returns(JsonSerializer.SerializeToElement(["CP1"], TestJsonSerializerContext.Default.StringArray));

        var session = new ChatClientAgentSession
        {
            AIContextProvider = mockProvider.Object
        };

        // Act
        var json = session.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("aiContextProviderState", out var providerStateProperty));
        Assert.Equal(JsonValueKind.Array, providerStateProperty.ValueKind);
        Assert.Single(providerStateProperty.EnumerateArray());
        Assert.Equal("CP1", providerStateProperty.EnumerateArray().First().GetString());
        mockProvider.Verify(m => m.Serialize(It.IsAny<JsonSerializerOptions?>()), Times.Once);
    }

    /// <summary>
    /// Verify session serialization to JSON with custom options.
    /// </summary>
    [Fact]
    public void VerifySessionSerializationWithCustomOptions()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        JsonSerializerOptions options = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);

        var chatHistoryProviderStateElement = JsonSerializer.SerializeToElement(
            new Dictionary<string, object> { ["Key"] = "TestValue" },
            TestJsonSerializerContext.Default.DictionaryStringObject);

        var chatHistoryProviderMock = new Mock<ChatHistoryProvider>();
        chatHistoryProviderMock
            .Setup(m => m.Serialize(options))
            .Returns(chatHistoryProviderStateElement);
        session.ChatHistoryProvider = chatHistoryProviderMock.Object;

        // Act
        var json = session.Serialize(options);

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.False(json.TryGetProperty("conversationId", out var idProperty));

        Assert.True(json.TryGetProperty("chatHistoryProviderState", out var chatHistoryProviderStateProperty));
        Assert.Equal(JsonValueKind.Object, chatHistoryProviderStateProperty.ValueKind);

        Assert.True(chatHistoryProviderStateProperty.TryGetProperty("Key", out var keyProperty));
        Assert.Equal("TestValue", keyProperty.GetString());

        chatHistoryProviderMock.Verify(m => m.Serialize(options), Times.Once);
    }

    #endregion Serialize Tests

    #region GetService Tests

    [Fact]
    public void GetService_RequestingAIContextProvider_ReturnsAIContextProvider()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var mockProvider = new Mock<AIContextProvider>();
        mockProvider
            .Setup(m => m.GetService(It.Is<Type>(x => x == typeof(AIContextProvider)), null))
            .Returns(mockProvider.Object);
        session.AIContextProvider = mockProvider.Object;

        // Act
        var result = session.GetService(typeof(AIContextProvider));

        // Assert
        Assert.NotNull(result);
        Assert.Same(mockProvider.Object, result);
    }

    [Fact]
    public void GetService_RequestingChatHistoryProvider_ReturnsChatHistoryProvider()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var chatHistoryProvider = new InMemoryChatHistoryProvider();
        session.ChatHistoryProvider = chatHistoryProvider;

        // Act
        var result = session.GetService(typeof(ChatHistoryProvider));

        // Assert
        Assert.NotNull(result);
        Assert.Same(chatHistoryProvider, result);
    }

    #endregion

    internal sealed class Animal
    {
        public string Name { get; set; } = string.Empty;
    }
}
