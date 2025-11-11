// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using A2A;
using Microsoft.Agents.AI.Hosting.A2A.Converters;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests.Converters;

public class MessageConverterTests
{
    [Fact]
    public void ToChatMessages_MessageSendParams_Null_ReturnsEmptyCollection()
    {
        MessageSendParams? messageSendParams = null;

        var result = messageSendParams!.ToChatMessages();

        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void ToChatMessages_MessageSendParams_WithNullMessage_ReturnsEmptyCollection()
    {
        var messageSendParams = new MessageSendParams
        {
            Message = null!
        };

        var result = messageSendParams.ToChatMessages();

        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void ToChatMessages_MessageSendParams_WithMessageWithoutParts_ReturnsEmptyCollection()
    {
        var messageSendParams = new MessageSendParams
        {
            Message = new AgentMessage
            {
                MessageId = "test-id",
                Role = MessageRole.User,
                Parts = null!
            }
        };

        var result = messageSendParams.ToChatMessages();

        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void ToChatMessages_MessageSendParams_WithValidTextMessage_ReturnsCorrectChatMessage()
    {
        var messageSendParams = new MessageSendParams
        {
            Message = new AgentMessage
            {
                MessageId = "test-id",
                Role = MessageRole.User,
                Parts =
                [
                    new TextPart { Text = "Hello, world!" }
                ]
            }
        };

        var result = messageSendParams.ToChatMessages();

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
