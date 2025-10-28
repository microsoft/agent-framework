// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AGUIChatMessageExtensions"/> class.
/// </summary>
public sealed class AGUIChatMessageExtensionsTests
{
    [Fact]
    public void AsChatMessages_WithEmptyCollection_ReturnsEmptyList()
    {
        // Arrange
        List<AGUIMessage> aguiMessages = [];

        // Act
        IEnumerable<ChatMessage> chatMessages = aguiMessages.AsChatMessages();

        // Assert
        Assert.NotNull(chatMessages);
        Assert.Empty(chatMessages);
    }

    [Fact]
    public void AsChatMessages_WithSingleMessage_ConvertsToChatMessageCorrectly()
    {
        // Arrange
        List<AGUIMessage> aguiMessages =
        [
            new AGUIMessage
            {
                Id = "msg1",
                Role = AGUIRoles.User,
                Content = "Hello"
            }
        ];

        // Act
        IEnumerable<ChatMessage> chatMessages = aguiMessages.AsChatMessages();

        // Assert
        ChatMessage message = Assert.Single(chatMessages);
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal("Hello", message.Text);
    }

    [Fact]
    public void AsChatMessages_WithMultipleMessages_PreservesOrder()
    {
        // Arrange
        List<AGUIMessage> aguiMessages =
        [
            new AGUIMessage { Id = "msg1", Role = AGUIRoles.User, Content = "First" },
            new AGUIMessage { Id = "msg2", Role = AGUIRoles.Assistant, Content = "Second" },
            new AGUIMessage { Id = "msg3", Role = AGUIRoles.User, Content = "Third" }
        ];

        // Act
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages().ToList();

        // Assert
        Assert.Equal(3, chatMessages.Count);
        Assert.Equal("First", chatMessages[0].Text);
        Assert.Equal("Second", chatMessages[1].Text);
        Assert.Equal("Third", chatMessages[2].Text);
    }

    [Fact]
    public void AsChatMessages_MapsAllSupportedRoleTypes_Correctly()
    {
        // Arrange
        List<AGUIMessage> aguiMessages =
        [
            new AGUIMessage { Id = "msg1", Role = AGUIRoles.System, Content = "System message" },
            new AGUIMessage { Id = "msg2", Role = AGUIRoles.User, Content = "User message" },
            new AGUIMessage { Id = "msg3", Role = AGUIRoles.Assistant, Content = "Assistant message" },
            new AGUIMessage { Id = "msg4", Role = AGUIRoles.Developer, Content = "Developer message" }
        ];

        // Act
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages().ToList();

        // Assert
        Assert.Equal(4, chatMessages.Count);
        Assert.Equal(ChatRole.System, chatMessages[0].Role);
        Assert.Equal(ChatRole.User, chatMessages[1].Role);
        Assert.Equal(ChatRole.Assistant, chatMessages[2].Role);
        Assert.Equal("developer", chatMessages[3].Role.Value);
    }

    [Fact]
    public void AsAGUIMessages_WithEmptyCollection_ReturnsEmptyList()
    {
        // Arrange
        List<ChatMessage> chatMessages = [];

        // Act
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages();

        // Assert
        Assert.NotNull(aguiMessages);
        Assert.Empty(aguiMessages);
    }

    [Fact]
    public void AsAGUIMessages_WithSingleMessage_ConvertsToAGUIMessageCorrectly()
    {
        // Arrange
        List<ChatMessage> chatMessages =
        [
            new ChatMessage(ChatRole.User, "Hello") { MessageId = "msg1" }
        ];

        // Act
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages();

        // Assert
        AGUIMessage message = Assert.Single(aguiMessages);
        Assert.Equal("msg1", message.Id);
        Assert.Equal(AGUIRoles.User, message.Role);
        Assert.Equal("Hello", message.Content);
    }

    [Fact]
    public void AsAGUIMessages_WithMultipleMessages_PreservesOrder()
    {
        // Arrange
        List<ChatMessage> chatMessages =
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Second"),
            new ChatMessage(ChatRole.User, "Third")
        ];

        // Act
        List<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages().ToList();

        // Assert
        Assert.Equal(3, aguiMessages.Count);
        Assert.Equal("First", aguiMessages[0].Content);
        Assert.Equal("Second", aguiMessages[1].Content);
        Assert.Equal("Third", aguiMessages[2].Content);
    }

    [Fact]
    public void AsAGUIMessages_PreservesMessageId_WhenPresent()
    {
        // Arrange
        List<ChatMessage> chatMessages =
        [
            new ChatMessage(ChatRole.User, "Hello") { MessageId = "msg123" }
        ];

        // Act
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages();

        // Assert
        AGUIMessage message = Assert.Single(aguiMessages);
        Assert.Equal("msg123", message.Id);
    }

    [Theory]
    [InlineData(AGUIRoles.System, "system")]
    [InlineData(AGUIRoles.User, "user")]
    [InlineData(AGUIRoles.Assistant, "assistant")]
    [InlineData(AGUIRoles.Developer, "developer")]
    public void MapChatRole_WithValidRole_ReturnsCorrectChatRole(string aguiRole, string expectedRoleValue)
    {
        // Arrange & Act
        ChatRole role = AGUIChatMessageExtensions.MapChatRole(aguiRole);

        // Assert
        Assert.Equal(expectedRoleValue, role.Value);
    }

    [Fact]
    public void MapChatRole_WithUnknownRole_ThrowsInvalidOperationException()
    {
        // Arrange & Act & Assert
        Assert.Throws<InvalidOperationException>(() => AGUIChatMessageExtensions.MapChatRole("unknown"));
    }
}
