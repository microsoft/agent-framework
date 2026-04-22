// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using A2A;
using Microsoft.Agents.AI.Hosting.A2A.Converters;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests.Converters;

public class MessageConverterTests
{
    [Fact]
    public void ToChatMessages_SendMessageRequest_Null_ReturnsEmptyCollection()
    {
        SendMessageRequest? sendMessageRequest = null;

        var result = sendMessageRequest!.ToChatMessages();

        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void ToChatMessages_SendMessageRequest_WithNullMessage_ReturnsEmptyCollection()
    {
        var sendMessageRequest = new SendMessageRequest
        {
            Message = null!
        };

        var result = sendMessageRequest.ToChatMessages();

        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void ToChatMessages_SendMessageRequest_WithMessageWithoutParts_ReturnsEmptyCollection()
    {
        var sendMessageRequest = new SendMessageRequest
        {
            Message = new Message
            {
                MessageId = "test-id",
                Role = Role.User,
                Parts = null!
            }
        };

        var result = sendMessageRequest.ToChatMessages();

        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void ToChatMessages_SendMessageRequest_WithValidTextMessage_ReturnsCorrectChatMessage()
    {
        var sendMessageRequest = new SendMessageRequest
        {
            Message = new Message
            {
                MessageId = "test-id",
                Role = Role.User,
                Parts =
                [
                    new Part { Text = "Hello, world!" }
                ]
            }
        };

        var result = sendMessageRequest.ToChatMessages();

        Assert.NotNull(result);
        Assert.Single(result);

        var chatMessage = result.First();
        Assert.Equal("test-id", chatMessage.MessageId);
        Assert.Equal(ChatRole.User, chatMessage.Role);
        Assert.Single(chatMessage.Contents);

        var textContent = Assert.IsType<TextContent>(chatMessage.Contents.First());
        Assert.Equal("Hello, world!", textContent.Text);
    }

    [Fact]
    public void ToParts_NullList_ReturnsEmptyList()
    {
        // Arrange
        IList<ChatMessage>? messages = null;

        // Act
        var result = messages!.ToParts();

        // Assert
        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void ToParts_EmptyList_ReturnsEmptyList()
    {
        // Arrange
        IList<ChatMessage> messages = [];

        // Act
        var result = messages.ToParts();

        // Assert
        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void ToParts_WithTextContent_ReturnsTextPart()
    {
        // Arrange
        IList<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.Assistant, "Hello from the agent!")
        ];

        // Act
        var result = messages.ToParts();

        // Assert
        Assert.Single(result);
        Assert.Equal("Hello from the agent!", result[0].Text);
    }

    [Fact]
    public void ToParts_WithMultipleMessages_ReturnsAllParts()
    {
        // Arrange
        IList<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "First message"),
            new ChatMessage(ChatRole.Assistant, "Second message")
        ];

        // Act
        var result = messages.ToParts();

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("First message", result[0].Text);
        Assert.Equal("Second message", result[1].Text);
    }
}
