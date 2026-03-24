// Copyright (c) Microsoft. All rights reserved.

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
                    Part.FromText("Hello, world!")
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
}
