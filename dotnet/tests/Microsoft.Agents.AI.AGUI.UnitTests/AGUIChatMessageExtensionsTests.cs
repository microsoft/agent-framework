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
        IEnumerable<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options);

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
        IEnumerable<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options);

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
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options).ToList();

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
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options).ToList();

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
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options);

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
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options);

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
        List<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options).ToList();

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
        IEnumerable<AGUIMessage> aguiMessages = chatMessages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options);

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

    [Fact]
    public void AsAGUIMessages_WithToolResultMessage_SerializesResultCorrectly()
    {
        // Arrange
        var result = new Dictionary<string, object?> { ["temperature"] = 72, ["condition"] = "Sunny" };
        FunctionResultContent toolResult = new("call_123", result);
        ChatMessage toolMessage = new(ChatRole.Tool, [toolResult]);
        List<ChatMessage> messages = [toolMessage];

        // Act
        List<AGUIMessage> aguiMessages = messages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        AGUIMessage aguiMessage = Assert.Single(aguiMessages);
        Assert.Equal(AGUIRoles.Tool, aguiMessage.Role);
        Assert.Equal("call_123", aguiMessage.CallId);
        Assert.NotEmpty(aguiMessage.Content);
        // Content should be serialized JSON
        Assert.Contains("temperature", aguiMessage.Content);
        Assert.Contains("72", aguiMessage.Content);
    }

    [Fact]
    public void AsAGUIMessages_WithNullToolResult_HandlesGracefully()
    {
        // Arrange
        FunctionResultContent toolResult = new("call_456", null);
        ChatMessage toolMessage = new(ChatRole.Tool, [toolResult]);
        List<ChatMessage> messages = [toolMessage];

        // Act
        List<AGUIMessage> aguiMessages = messages.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        AGUIMessage aguiMessage = Assert.Single(aguiMessages);
        Assert.Equal(AGUIRoles.Tool, aguiMessage.Role);
        Assert.Equal("call_456", aguiMessage.CallId);
        Assert.Equal(string.Empty, aguiMessage.Content);
    }

    [Fact]
    public void AsAGUIMessages_WithoutTypeInfoResolver_ThrowsInvalidOperationException()
    {
        // Arrange
        FunctionResultContent toolResult = new("call_789", "Result");
        ChatMessage toolMessage = new(ChatRole.Tool, [toolResult]);
        List<ChatMessage> messages = [toolMessage];
        System.Text.Json.JsonSerializerOptions optionsWithoutResolver = new();

        // Act & Assert
        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() => messages.AsAGUIMessages(optionsWithoutResolver).ToList());
        Assert.Contains("TypeInfoResolver", ex.Message);
        Assert.Contains("AOT-compatible", ex.Message);
    }

    [Fact]
    public void AsChatMessages_WithToolMessage_DeserializesResultCorrectly()
    {
        // Arrange
        const string JsonContent = "{\"status\":\"success\",\"value\":42}";
        List<AGUIMessage> aguiMessages =
        [
            new AGUIMessage
            {
                Id = "msg1",
                Role = AGUIRoles.Tool,
                Content = JsonContent,
                CallId = "call_abc"
            }
        ];

        // Act
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        ChatMessage message = Assert.Single(chatMessages);
        Assert.Equal(ChatRole.Tool, message.Role);
        FunctionResultContent result = Assert.IsType<FunctionResultContent>(message.Contents[0]);
        Assert.Equal("call_abc", result.CallId);
        Assert.NotNull(result.Result);
    }

    [Fact]
    public void AsChatMessages_WithEmptyToolContent_CreatesNullResult()
    {
        // Arrange
        List<AGUIMessage> aguiMessages =
        [
            new AGUIMessage
            {
                Id = "msg1",
                Role = AGUIRoles.Tool,
                Content = string.Empty,
                CallId = "call_def"
            }
        ];

        // Act
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        ChatMessage message = Assert.Single(chatMessages);
        FunctionResultContent result = Assert.IsType<FunctionResultContent>(message.Contents[0]);
        Assert.Equal("call_def", result.CallId);
        Assert.Equal(string.Empty, result.Result);
    }

    [Fact]
    public void AsChatMessages_WithToolMessageWithoutCallId_TreatsAsRegularMessage()
    {
        // Arrange
        List<AGUIMessage> aguiMessages =
        [
            new AGUIMessage
            {
                Id = "msg1",
                Role = AGUIRoles.Tool,
                Content = "Some content",
                CallId = null
            }
        ];

        // Act
        List<ChatMessage> chatMessages = aguiMessages.AsChatMessages(AGUIJsonSerializerContext.Default.Options).ToList();

        // Assert
        ChatMessage message = Assert.Single(chatMessages);
        Assert.Equal(ChatRole.Tool, message.Role);
        Assert.Equal("Some content", message.Text);
    }

    [Fact]
    public void RoundTrip_ToolResultMessage_PreservesData()
    {
        // Arrange
        var resultData = new Dictionary<string, object?> { ["location"] = "Seattle", ["temperature"] = 68, ["forecast"] = "Partly cloudy" };
        FunctionResultContent originalResult = new("call_roundtrip", resultData);
        ChatMessage originalMessage = new(ChatRole.Tool, [originalResult]);

        // Act - Convert to AGUI and back
        List<ChatMessage> originalList = [originalMessage];
        AGUIMessage aguiMessage = originalList.AsAGUIMessages(AGUIJsonSerializerContext.Default.Options).Single();
        List<AGUIMessage> aguiList = [aguiMessage];
        ChatMessage reconstructedMessage = aguiList.AsChatMessages(AGUIJsonSerializerContext.Default.Options).Single();

        // Assert
        Assert.Equal(ChatRole.Tool, reconstructedMessage.Role);
        FunctionResultContent reconstructedResult = Assert.IsType<FunctionResultContent>(reconstructedMessage.Contents[0]);
        Assert.Equal("call_roundtrip", reconstructedResult.CallId);
        Assert.NotNull(reconstructedResult.Result);
    }

    [Fact]
    public void MapChatRole_WithToolRole_ReturnsToolChatRole()
    {
        // Arrange & Act
        ChatRole role = AGUIChatMessageExtensions.MapChatRole(AGUIRoles.Tool);

        // Assert
        Assert.Equal(ChatRole.Tool, role);
    }
}
