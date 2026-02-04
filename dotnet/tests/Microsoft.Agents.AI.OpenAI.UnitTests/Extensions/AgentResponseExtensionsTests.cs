// Copyright (c) Microsoft. All rights reserved.

using System;
using OpenAI.Chat;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;
using ChatRole = Microsoft.Extensions.AI.ChatRole;
using TextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.OpenAI.UnitTests.Extensions;

/// <summary>
/// Unit tests for the AgentResponseExtensions class that provides OpenAI extension methods.
/// </summary>
public sealed class AgentResponseExtensionsTests
{
    /// <summary>
    /// Verify that AsOpenAIChatCompletion throws ArgumentNullException when response is null.
    /// </summary>
    [Fact]
    public void AsOpenAIChatCompletion_WithNullResponse_ThrowsArgumentNullException()
    {
        // Arrange
        AgentResponse? response = null;

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(
            () => response!.AsOpenAIChatCompletion());

        Assert.Equal("response", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsOpenAIChatCompletion returns the RawRepresentation when it is a ChatCompletion.
    /// </summary>
    [Fact]
    public void AsOpenAIChatCompletion_WithChatCompletionRawRepresentation_ReturnsChatCompletion()
    {
        // Arrange
        ChatCompletion chatCompletion = ModelReaderWriterHelper.CreateChatCompletion("assistant_id", "Hello");
        var responseMessage = new ChatMessage(ChatRole.Assistant, [new TextContent("Hello")]);
        var agentResponse = new AgentResponse([responseMessage])
        {
            RawRepresentation = chatCompletion
        };

        // Act
        ChatCompletion result = agentResponse.AsOpenAIChatCompletion();

        // Assert
        Assert.NotNull(result);
        Assert.Same(chatCompletion, result);
    }

    /// <summary>
    /// Verify that AsOpenAIChatCompletion converts a ChatResponse when RawRepresentation is not a ChatCompletion.
    /// </summary>
    [Fact]
    public void AsOpenAIChatCompletion_WithNonChatCompletionRawRepresentation_ConvertsChatResponse()
    {
        // Arrange
        const string ResponseText = "This is a test response.";
        var responseMessage = new ChatMessage(ChatRole.Assistant, [new TextContent(ResponseText)]);
        var agentResponse = new AgentResponse([responseMessage]);

        // Act
        ChatCompletion result = agentResponse.AsOpenAIChatCompletion();

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Content);
        Assert.Equal(ResponseText, result.Content[0].Text);
    }

    /// <summary>
    /// Verify that AsOpenAIResponse throws ArgumentNullException when response is null.
    /// </summary>
    [Fact]
    public void AsOpenAIResponse_WithNullResponse_ThrowsArgumentNullException()
    {
        // Arrange
        AgentResponse? response = null;

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(
            () => response!.AsOpenAIResponse());

        Assert.Equal("response", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsOpenAIResponse converts a ChatResponse when RawRepresentation is not a ResponseResult.
    /// </summary>
    [Fact]
    public void AsOpenAIResponse_WithNonResponseResultRawRepresentation_ConvertsChatResponse()
    {
        // Arrange
        const string ResponseText = "This is a test response.";
        var responseMessage = new ChatMessage(ChatRole.Assistant, [new TextContent(ResponseText)]);
        var agentResponse = new AgentResponse([responseMessage]);

        // Act
        var result = agentResponse.AsOpenAIResponse();

        // Assert
        Assert.NotNull(result);
    }
}

/// <summary>
/// Helper class for creating OpenAI model objects using ModelReaderWriter.
/// </summary>
internal static class ModelReaderWriterHelper
{
    public static ChatCompletion CreateChatCompletion(string id, string contentText)
    {
        string json = $$"""
        {
            "id": "{{id}}",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "gpt-4",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "{{contentText}}"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 10,
                "total_tokens": 20
            }
        }
        """;

        return System.ClientModel.Primitives.ModelReaderWriter.Read<ChatCompletion>(BinaryData.FromString(json))!;
    }
}
