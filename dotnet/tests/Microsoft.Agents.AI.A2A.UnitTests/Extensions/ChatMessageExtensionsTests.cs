// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using A2A;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="ChatMessageExtensions"/> class.
/// </summary>
public sealed class ChatMessageExtensionsTests
{
    [Fact]
    public void ToA2AMessage_WithMessageContainingMultipleContents_AddsAllContentsAsParts()
    {
        // Arrange
        var contents = new List<AIContent>
        {
            new UriContent("https://example.com/report.pdf", "file/pdf"),
            new TextContent("please summarize the file content"),
            new TextContent("and send it to me over email")
        };
        var chatMessage = new ChatMessage(ChatRole.User, contents);
        var messages = new List<ChatMessage> { chatMessage };

        // Act
        var a2aMessage = messages.ToA2AMessage();

        // Assert
        Assert.NotNull(a2aMessage);
        Assert.NotNull(a2aMessage.MessageId);
        Assert.NotEmpty(a2aMessage.MessageId);

        Assert.Equal(Role.User, a2aMessage.Role);

        Assert.NotNull(a2aMessage.Parts);
        Assert.Equal(3, a2aMessage.Parts.Count);

        Assert.Equal(PartContentCase.Url, a2aMessage.Parts[0].ContentCase);
        Assert.Equal("https://example.com/report.pdf", a2aMessage.Parts[0].Url);

        Assert.Equal(PartContentCase.Text, a2aMessage.Parts[1].ContentCase);
        Assert.Equal("please summarize the file content", a2aMessage.Parts[1].Text);

        Assert.Equal(PartContentCase.Text, a2aMessage.Parts[2].ContentCase);
        Assert.Equal("and send it to me over email", a2aMessage.Parts[2].Text);
    }

    [Fact]
    public void ToA2AMessage_WithMixedMessages_AddsAllContentsAsParts()
    {
        // Arrange
        var firstMessage = new ChatMessage(ChatRole.User, [
            new UriContent("https://example.com/report.pdf", "file/pdf"),
        ]);
        var secondMessage = new ChatMessage(ChatRole.User, [
            new TextContent("please summarize the file content")
        ]);
        var thirdMessage = new ChatMessage(ChatRole.User, [
            new TextContent("and send it to me over email")
        ]);
        var messages = new List<ChatMessage> { firstMessage, secondMessage, thirdMessage };

        // Act
        var a2aMessage = messages.ToA2AMessage();

        // Assert
        Assert.NotNull(a2aMessage);
        Assert.NotNull(a2aMessage.MessageId);
        Assert.NotEmpty(a2aMessage.MessageId);

        Assert.Equal(Role.User, a2aMessage.Role);

        Assert.NotNull(a2aMessage.Parts);
        Assert.Equal(3, a2aMessage.Parts.Count);

        Assert.Equal(PartContentCase.Url, a2aMessage.Parts[0].ContentCase);
        Assert.Equal("https://example.com/report.pdf", a2aMessage.Parts[0].Url);

        Assert.Equal(PartContentCase.Text, a2aMessage.Parts[1].ContentCase);
        Assert.Equal("please summarize the file content", a2aMessage.Parts[1].Text);

        Assert.Equal(PartContentCase.Text, a2aMessage.Parts[2].ContentCase);
        Assert.Equal("and send it to me over email", a2aMessage.Parts[2].Text);
    }
}
