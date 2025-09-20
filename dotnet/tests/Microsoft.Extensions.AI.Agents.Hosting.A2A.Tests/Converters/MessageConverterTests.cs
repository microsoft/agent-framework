// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using A2A;
using Microsoft.Extensions.AI.Agents.Hosting.A2A.Converters;

namespace Microsoft.Extensions.AI.Agents.Hosting.A2A.Tests.Converters;

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
            Message = new Message
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
            Message = new Message
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

    [Fact]
    public void ToChatMessages_MessageCollection_Null_ReturnsEmptyCollection()
    {
        ICollection<Message>? messages = null;

        var result = messages!.ToChatMessages();

        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void ToChatMessages_MessageCollection_Empty_ReturnsEmptyCollection()
    {
        var messages = new List<Message>();

        var result = messages.ToChatMessages();

        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void ToChatMessages_MessageCollection_WithValidMessages_ReturnsCorrectChatMessages()
    {
        var messages = new List<Message>
        {
            new()
            {
                MessageId = "user-msg",
                Role = MessageRole.User,
                Parts = [new TextPart { Text = "User message" }]
            },
            new()
            {
                MessageId = "agent-msg",
                Role = MessageRole.Agent,
                Parts = [new TextPart { Text = "Agent response" }]
            }
        };

        var result = messages.ToChatMessages();

        Assert.NotNull(result);
        Assert.Equal(2, result.Count);

        var userMessage = result.First();
        Assert.Equal("user-msg", userMessage.MessageId);
        Assert.Equal(ChatRole.User, userMessage.Role);
        Assert.Equal("User message", ((TextContent)userMessage.Contents.First()).Text);

        var agentMessage = result.Skip(1).First();
        Assert.Equal("agent-msg", agentMessage.MessageId);
        Assert.Equal(ChatRole.Assistant, agentMessage.Role);
        Assert.Equal("Agent response", ((TextContent)agentMessage.Contents.First()).Text);
    }

    [Fact]
    public void ToChatMessages_MessageCollection_SkipsInvalidMessages_ReturnsValidChatMessages()
    {
        var messages = new List<Message>
        {
            new()
            {
                MessageId = "valid-msg",
                Role = MessageRole.User,
                Parts = [new TextPart { Text = "Valid message" }]
            },
            new()
            {
                MessageId = "invalid-msg",
                Role = MessageRole.User,
                Parts = null! // Invalid - no parts
            }
        };

        var result = messages.ToChatMessages();

        Assert.NotNull(result);
        Assert.Single(result);

        var validMessage = result.First();
        Assert.Equal("valid-msg", validMessage.MessageId);
        Assert.Equal("Valid message", ((TextContent)validMessage.Contents.First()).Text);
    }

    [Fact]
    public void ToA2AMessage_NullChatMessage_ThrowsArgumentNullException()
    {
        ChatMessage? chatMessage = null;

        Assert.Throws<ArgumentNullException>(() => chatMessage!.ToA2AMessage());
    }

    [Fact]
    public void ToA2AMessage_ValidChatMessage_ReturnsCorrectA2AMessage()
    {
        var chatMessage = new ChatMessage(ChatRole.User, "Hello, world!")
        {
            MessageId = "test-id"
        };

        var result = chatMessage.ToA2AMessage();

        Assert.NotNull(result);
        Assert.Equal("test-id", result.MessageId);
        Assert.Equal(MessageRole.User, result.Role);
        Assert.Single(result.Parts);

        var textPart = Assert.IsType<TextPart>(result.Parts.First());
        Assert.Equal("Hello, world!", textPart.Text);
    }

    [Fact]
    public void ToA2AMessage_ChatMessageWithoutMessageId_GeneratesNewMessageId()
    {
        var chatMessage = new ChatMessage(ChatRole.Assistant, "Response message");

        var result = chatMessage.ToA2AMessage();

        Assert.NotNull(result);
        Assert.NotNull(result.MessageId);
        Assert.NotEmpty(result.MessageId);
        Assert.Equal(MessageRole.Agent, result.Role);
    }

    [Fact]
    public void ToA2AMessage_ChatMessageWithTextContent_ReturnsCorrectTextPart()
    {
        var textContent = new TextContent("Test content");
        var chatMessage = new ChatMessage(ChatRole.User, [textContent]);

        var result = chatMessage.ToA2AMessage();

        Assert.NotNull(result);
        Assert.Single(result.Parts);

        var textPart = Assert.IsType<TextPart>(result.Parts.First());
        Assert.Equal("Test content", textPart.Text);
    }

    [Fact]
    public void ToA2AMessage_ChatMessageWithUnsupportedContent_ThrowsNotSupportedException()
    {
        var unsupportedContent = new DataContent(new byte[] { 1, 2, 3 }, "image/png");
        var chatMessage = new ChatMessage(ChatRole.User, [unsupportedContent]);

        var exception = Assert.Throws<NotSupportedException>(chatMessage.ToA2AMessage);
        Assert.Contains("Content type 'DataContent' is not supported", exception.Message);
    }

    [Fact]
    public void ToA2AMessage_ChatMessageWithEmptyContent_CreatesTextPartFromMessageText()
    {
        var chatMessage = new ChatMessage(ChatRole.User, "Fallback text");

        var result = chatMessage.ToA2AMessage();

        Assert.NotNull(result);
        Assert.Single(result.Parts);

        var textPart = Assert.IsType<TextPart>(result.Parts.First());
        Assert.Equal("Fallback text", textPart.Text);
    }

    [Fact]
    public void ConvertMessageRoleToChatRole_UserRole_ReturnsUserChatRole()
    {
        var message = new Message
        {
            MessageId = "test",
            Role = MessageRole.User,
            Parts = [new TextPart { Text = "Test" }]
        };

        var result = new List<Message> { message }.ToChatMessages();

        var chatMessage = result.First();
        Assert.Equal(ChatRole.User, chatMessage.Role);
    }

    [Fact]
    public void ConvertMessageRoleToChatRole_AgentRole_ReturnsAssistantChatRole()
    {
        var message = new Message
        {
            MessageId = "test",
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Test" }]
        };

        var result = new List<Message> { message }.ToChatMessages();

        var chatMessage = result.First();
        Assert.Equal(ChatRole.Assistant, chatMessage.Role);
    }

    [Fact]
    public void ConvertMessageRoleToChatRole_UnknownRole_ReturnsUserChatRole()
    {
        var message = new Message
        {
            MessageId = "test",
            Role = (MessageRole)999, // Unknown role
            Parts = [new TextPart { Text = "Test" }]
        };

        var result = new List<Message> { message }.ToChatMessages();

        var chatMessage = result.First();
        Assert.Equal(ChatRole.User, chatMessage.Role);
    }

    [Fact]
    public void ConvertChatRoleToMessageRole_UserRole_ReturnsUserMessageRole()
    {
        var chatMessage = new ChatMessage(ChatRole.User, "Test message");

        var result = chatMessage.ToA2AMessage();

        Assert.Equal(MessageRole.User, result.Role);
    }

    [Fact]
    public void ConvertChatRoleToMessageRole_AssistantRole_ReturnsAgentMessageRole()
    {
        var chatMessage = new ChatMessage(ChatRole.Assistant, "Test message");

        var result = chatMessage.ToA2AMessage();

        Assert.Equal(MessageRole.Agent, result.Role);
    }

    [Fact]
    public void ConvertChatRoleToMessageRole_SystemRole_ReturnsUserMessageRole()
    {
        var chatMessage = new ChatMessage(ChatRole.System, "Test message");

        var result = chatMessage.ToA2AMessage();

        Assert.Equal(MessageRole.User, result.Role);
    }

    [Fact]
    public void ConvertChatRoleToMessageRole_ToolRole_ReturnsUserMessageRole()
    {
        var chatMessage = new ChatMessage(ChatRole.Tool, "Test message");

        var result = chatMessage.ToA2AMessage();

        Assert.Equal(MessageRole.User, result.Role);
    }

    [Fact]
    public void ConvertPartToAIContent_TextPart_ReturnsTextContent()
    {
        var textPart = new TextPart { Text = "Sample text" };
        var message = new Message
        {
            MessageId = "test",
            Role = MessageRole.User,
            Parts = [textPart]
        };

        var result = new List<Message> { message }.ToChatMessages();

        var chatMessage = result.First();
        var textContent = Assert.IsType<TextContent>(chatMessage.Contents.First());
        Assert.Equal("Sample text", textContent.Text);
        Assert.Equal(textPart, textContent.RawRepresentation);
    }

    [Fact]
    public void ConvertPartToAIContent_TextPartWithMetadata_PreservesMetadata()
    {
        var metadata = new Dictionary<string, JsonElement>
        {
            ["key1"] = JsonDocument.Parse("\"value1\"").RootElement,
            ["key2"] = JsonDocument.Parse("42").RootElement
        };
        var textPart = new TextPart
        {
            Text = "Text with metadata",
            Metadata = metadata
        };
        var message = new Message
        {
            MessageId = "test",
            Role = MessageRole.User,
            Parts = [textPart]
        };

        var result = new List<Message> { message }.ToChatMessages();

        var chatMessage = result.First();
        var textContent = Assert.IsType<TextContent>(chatMessage.Contents.First());
        Assert.NotNull(textContent.AdditionalProperties);
        Assert.Equal(2, textContent.AdditionalProperties.Count);
        Assert.True(textContent.AdditionalProperties.ContainsKey("key1"));
        Assert.True(textContent.AdditionalProperties.ContainsKey("key2"));
    }

    [Fact]
    public void ConvertPartToAIContent_FilePart_ThrowsNotSupportedException()
    {
        var filePart = new FilePart();
        var message = new Message
        {
            MessageId = "test",
            Role = MessageRole.User,
            Parts = [filePart]
        };

        var exception = Assert.Throws<NotSupportedException>(() => new List<Message> { message }.ToChatMessages());
        Assert.Contains("Part type 'FilePart' is not supported", exception.Message);
    }

    [Fact]
    public void ConvertPartToAIContent_DataPart_ThrowsNotSupportedException()
    {
        var dataPart = new DataPart();
        var message = new Message
        {
            MessageId = "test",
            Role = MessageRole.User,
            Parts = [dataPart]
        };

        var exception = Assert.Throws<NotSupportedException>(() => new List<Message> { message }.ToChatMessages());
        Assert.Contains("Part type 'DataPart' is not supported", exception.Message);
    }

    [Fact]
    public void ConvertMessageToChatMessage_WithMetadata_PreservesMetadataInAdditionalProperties()
    {
        var metadata = new Dictionary<string, JsonElement>
        {
            ["timestamp"] = JsonDocument.Parse("\"2024-01-01T00:00:00Z\"").RootElement,
            ["priority"] = JsonDocument.Parse("1").RootElement
        };
        var message = new Message
        {
            MessageId = "test-id",
            Role = MessageRole.User,
            Parts = [new TextPart { Text = "Test" }],
            Metadata = metadata
        };

        var result = new List<Message> { message }.ToChatMessages();

        var chatMessage = result.First();
        Assert.NotNull(chatMessage.AdditionalProperties);
        Assert.Equal(2, chatMessage.AdditionalProperties.Count);
        Assert.True(chatMessage.AdditionalProperties.ContainsKey("timestamp"));
        Assert.True(chatMessage.AdditionalProperties.ContainsKey("priority"));
    }

    [Fact]
    public void ConvertMessageToChatMessage_WithRawRepresentation_PreservesOriginalMessage()
    {
        var message = new Message
        {
            MessageId = "test-id",
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Test response" }]
        };

        var result = new List<Message> { message }.ToChatMessages();

        var chatMessage = result.First();
        Assert.Equal(message, chatMessage.RawRepresentation);
    }

    [Fact]
    public void ToChatMessages_MessageWithEmptyParts_ReturnsEmptyCollection()
    {
        var message = new Message
        {
            MessageId = "test-id",
            Role = MessageRole.User,
            Parts = [] // Empty list
        };

        var result = new List<Message> { message }.ToChatMessages();

        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void ToA2AMessage_ChatMessageWithMultipleTextContents_CreatesMultipleParts()
    {
        var contents = new List<AIContent>
        {
            new TextContent("First part"),
            new TextContent("Second part")
        };
        var chatMessage = new ChatMessage(ChatRole.User, contents);

        var result = chatMessage.ToA2AMessage();

        Assert.NotNull(result);
        Assert.Equal(2, result.Parts.Count);

        var firstPart = Assert.IsType<TextPart>(result.Parts[0]);
        var secondPart = Assert.IsType<TextPart>(result.Parts[1]);
        Assert.Equal("First part", firstPart.Text);
        Assert.Equal("Second part", secondPart.Text);
    }

    [Fact]
    public void ToAdditionalPropertiesDictionary_NullMetadata_ReturnsNull()
    {
        var message = new Message
        {
            MessageId = "test-id",
            Role = MessageRole.User,
            Parts = [new TextPart { Text = "Test" }],
            Metadata = null
        };

        var result = new List<Message> { message }.ToChatMessages();

        var chatMessage = result.First();
        Assert.Null(chatMessage.AdditionalProperties);
    }

    [Fact]
    public void ToAdditionalPropertiesDictionary_EmptyMetadata_ReturnsNull()
    {
        var message = new Message
        {
            MessageId = "test-id",
            Role = MessageRole.User,
            Parts = [new TextPart { Text = "Test" }],
            Metadata = []
        };

        var result = new List<Message> { message }.ToChatMessages();

        var chatMessage = result.First();
        Assert.Null(chatMessage.AdditionalProperties);
    }
}
