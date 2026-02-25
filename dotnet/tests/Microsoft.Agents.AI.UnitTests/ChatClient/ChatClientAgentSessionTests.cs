// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;

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
    }

    #endregion Constructor and Property Tests

    #region Deserialize Tests

    [Fact]
    public void VerifyDeserializeWithMessages()
    {
        // Arrange
        var json = JsonSerializer.Deserialize("""
            {
                "stateBag": {
                    "InMemoryChatHistoryProvider": {
                        "messages": [{"authorName": "testAuthor"}]
                    }
                }
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act.
        var session = ChatClientAgentSession.Deserialize(json, TestJsonSerializerContext.Default.Options);

        // Assert
        Assert.Null(session.ConversationId);

        var chatHistoryProvider = new InMemoryChatHistoryProvider();
        var messages = chatHistoryProvider.GetMessages(session);
        Assert.Single(messages);
        Assert.Equal("testAuthor", messages[0].AuthorName);
    }

    [Fact]
    public void VerifyDeserializeWithId()
    {
        // Arrange
        var json = JsonSerializer.Deserialize("""
            {
                "conversationId": "TestConvId"
            }
            """, TestJsonSerializerContext.Default.JsonElement);

        // Act
        var session = ChatClientAgentSession.Deserialize(json);

        // Assert
        Assert.Equal("TestConvId", session.ConversationId);
    }

    [Fact]
    public void VerifyDeserializeWithStateBag()
    {
        // Arrange
        var json = JsonSerializer.Deserialize("""
            {
                "conversationId": "TestConvId",
                "stateBag": {
                    "dog": {
                        "name": "Fido"
                    }
                }
            }
            """, TestJsonSerializerContext.Default.JsonElement);
        // Act
        var session = ChatClientAgentSession.Deserialize(json);

        // Assert
        var dog = session.StateBag.GetValue<Animal>("dog", TestJsonSerializerContext.Default.Options);
        Assert.NotNull(dog);
        Assert.Equal("Fido", dog.Name);
    }

    [Fact]
    public void DeserializeWithInvalidJsonThrows()
    {
        // Arrange
        var invalidJson = JsonSerializer.Deserialize("[42]", TestJsonSerializerContext.Default.JsonElement);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => ChatClientAgentSession.Deserialize(invalidJson));
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
        var provider = new InMemoryChatHistoryProvider();
        var session = new ChatClientAgentSession();
        provider.SetMessages(session, [new(ChatRole.User, "TestContent") { AuthorName = "TestAuthor" }]);

        // Act
        var json = session.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        Assert.False(json.TryGetProperty("conversationId", out _));

        // Messages should be stored in the stateBag
        Assert.True(json.TryGetProperty("stateBag", out var stateBagProperty));
        Assert.Equal(JsonValueKind.Object, stateBagProperty.ValueKind);
        Assert.True(stateBagProperty.TryGetProperty("InMemoryChatHistoryProvider", out var providerStateProperty));
        Assert.Equal(JsonValueKind.Object, providerStateProperty.ValueKind);
        Assert.True(providerStateProperty.TryGetProperty("messages", out var messagesProperty));
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
    public void VerifySessionSerializationWithWithStateBag()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        session.StateBag.SetValue("dog", new Animal { Name = "Fido" }, TestJsonSerializerContext.Default.Options);

        // Act
        var json = session.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("stateBag", out var stateBagProperty));
        Assert.Equal(JsonValueKind.Object, stateBagProperty.ValueKind);
        Assert.True(stateBagProperty.TryGetProperty("dog", out var dogProperty));
        Assert.Equal(JsonValueKind.Object, dogProperty.ValueKind);
        Assert.True(dogProperty.TryGetProperty("name", out var nameProperty));
        Assert.Equal("Fido", nameProperty.GetString());
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
        options.TypeInfoResolverChain.Add(AgentJsonUtilities.DefaultOptions.TypeInfoResolver!);

        // Act
        var json = session.Serialize(options);

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);

        // [JsonPropertyName] takes precedence over naming policy
        Assert.True(json.TryGetProperty("conversationId", out var _));
    }

    #endregion Serialize Tests

    #region StateBag Roundtrip Tests

    [Fact]
    public void VerifyStateBagRoundtrips()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        session.StateBag.SetValue("dog", new Animal { Name = "Fido" }, TestJsonSerializerContext.Default.Options);

        // Act
        var serializedSession = session.Serialize();
        var deserializedSession = ChatClientAgentSession.Deserialize(serializedSession);

        // Assert
        var dog = deserializedSession.StateBag.GetValue<Animal>("dog", TestJsonSerializerContext.Default.Options);
        Assert.NotNull(dog);
        Assert.Equal("Fido", dog.Name);
    }

    #endregion

    internal sealed class Animal
    {
        public string Name { get; set; } = string.Empty;
    }
}
