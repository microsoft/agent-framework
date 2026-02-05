// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="StructuredOutputAgentResponse"/> class.
/// </summary>
public sealed class StructuredOutputAgentResponseTests
{
    [Fact]
    public void Constructor_WithValidParameters_SetsOriginalResponse()
    {
        // Arrange
        ChatResponse chatResponse = new([new ChatMessage(ChatRole.Assistant, "Structured output")]);
        AgentResponse originalResponse = new([new ChatMessage(ChatRole.Assistant, "Original response")]);

        // Act
        StructuredOutputAgentResponse structuredResponse = new(chatResponse, originalResponse);

        // Assert
        Assert.Same(originalResponse, structuredResponse.OriginalResponse);
    }

    [Fact]
    public void Constructor_WithValidParameters_InheritsFromAgentResponse()
    {
        // Arrange
        ChatResponse chatResponse = new([new ChatMessage(ChatRole.Assistant, "Structured output")]);
        AgentResponse originalResponse = new([new ChatMessage(ChatRole.Assistant, "Original response")]);

        // Act
        StructuredOutputAgentResponse structuredResponse = new(chatResponse, originalResponse);

        // Assert
        Assert.IsAssignableFrom<AgentResponse>(structuredResponse);
    }

    [Fact]
    public void OriginalResponse_ReturnsCorrectAgentResponse()
    {
        // Arrange
        ChatResponse chatResponse = new([new ChatMessage(ChatRole.Assistant, "Structured output")]);
        AgentResponse originalResponse = new([new ChatMessage(ChatRole.Assistant, "Original response")])
        {
            AgentId = "agent-1",
            ResponseId = "original-response-123"
        };

        // Act
        StructuredOutputAgentResponse structuredResponse = new(chatResponse, originalResponse);

        // Assert
        Assert.Same(originalResponse, structuredResponse.OriginalResponse);
        Assert.Equal("agent-1", structuredResponse.OriginalResponse.AgentId);
        Assert.Equal("original-response-123", structuredResponse.OriginalResponse.ResponseId);
    }

    [Fact]
    public void Text_ReturnsStructuredOutputText()
    {
        // Arrange
        const string StructuredJson = "{\"name\": \"Test\", \"value\": 42}";
        ChatResponse chatResponse = new([new ChatMessage(ChatRole.Assistant, StructuredJson)]);
        AgentResponse originalResponse = new([new ChatMessage(ChatRole.Assistant, "Original text response")]);

        // Act
        StructuredOutputAgentResponse structuredResponse = new(chatResponse, originalResponse);

        // Assert
        Assert.Equal(StructuredJson, structuredResponse.Text);
    }
}
