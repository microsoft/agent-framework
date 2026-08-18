// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for ChatCompletionRequestMessage.ToChatMessage() role preservation.
/// Verifies that each message type correctly maps its role to the corresponding ChatRole.
/// </summary>
public sealed class ChatCompletionRequestMessageToChatMessageTests
{
    [Theory]
    [InlineData("system", """{"role":"system","content":"You are a helpful assistant."}""")]
    [InlineData("developer", """{"role":"developer","content":"Follow these rules."}""")]
    [InlineData("user", """{"role":"user","content":"Hello!"}""")]
    [InlineData("assistant", """{"role":"assistant","content":"Hi there!"}""")]
    [InlineData("tool", """{"role":"tool","content":"result","tool_call_id":"call_123"}""")]
    public void ToChatMessage_PreservesRole_ForTextContent(string expectedRole, string json)
    {
        // Arrange
        ChatCompletionRequestMessage message = JsonSerializer.Deserialize(
            json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletionRequestMessage)!;

        // Act
        ChatMessage chatMessage = message.ToChatMessage();

        // Assert
        Assert.Equal(expectedRole, message.Role);
        Assert.Equal(new ChatRole(expectedRole), chatMessage.Role);
    }

    [Fact]
    public void ToChatMessage_FunctionMessage_PreservesRole()
    {
        // Arrange
        const string Json = """{"role":"function","name":"get_weather","content":"sunny"}""";
        ChatCompletionRequestMessage message = JsonSerializer.Deserialize(
            Json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletionRequestMessage)!;

        // Act
        ChatMessage chatMessage = message.ToChatMessage();

        // Assert
        Assert.Equal("function", message.Role);
        Assert.Equal(new ChatRole("function"), chatMessage.Role);
    }

    [Theory]
    [InlineData("system")]
    [InlineData("developer")]
    [InlineData("user")]
    [InlineData("assistant")]
    public void ToChatMessage_PreservesRole_ForMultiPartContent(string expectedRole)
    {
        // Arrange
        string json = $$"""{"role":"{{expectedRole}}","content":[{"type":"text","text":"Hello!"}]}""";
        ChatCompletionRequestMessage message = JsonSerializer.Deserialize(
            json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletionRequestMessage)!;

        // Act
        ChatMessage chatMessage = message.ToChatMessage();

        // Assert
        Assert.Equal(expectedRole, message.Role);
        Assert.Equal(new ChatRole(expectedRole), chatMessage.Role);
    }

    [Fact]
    public void ToChatMessage_MultiTurnConversation_PreservesAllRoles()
    {
        // Arrange - simulate a multi-turn conversation
        string[] jsons =
        [
            """{"role":"system","content":"You are a helpful assistant."}""",
            """{"role":"user","content":"Hello!"}""",
            """{"role":"assistant","content":"Hi there! How can I help?"}""",
            """{"role":"user","content":"What did I just say?"}"""
        ];

        string[] expectedRoles = ["system", "user", "assistant", "user"];

        // Act
        ChatMessage[] chatMessages = jsons
            .Select(j => JsonSerializer.Deserialize(
                j, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletionRequestMessage)!)
            .Select(m => m.ToChatMessage())
            .ToArray();

        // Assert
        Assert.Equal(expectedRoles.Length, chatMessages.Length);
        for (int i = 0; i < expectedRoles.Length; i++)
        {
            Assert.Equal(new ChatRole(expectedRoles[i]), chatMessages[i].Role);
        }
    }

    [Fact]
    public void ToChatMessage_PreservesTextContent()
    {
        // Arrange
        const string Json = """{"role":"system","content":"You are a helpful assistant."}""";
        ChatCompletionRequestMessage message = JsonSerializer.Deserialize(
            Json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletionRequestMessage)!;

        // Act
        ChatMessage chatMessage = message.ToChatMessage();

        // Assert
        Assert.Contains(chatMessage.Contents, c => c is TextContent tc && tc.Text == "You are a helpful assistant.");
    }
}
