// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask.State;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.Tests.Unit.State;

public sealed class DurableAgentStateResponseTests
{
    [Fact]
    public void FromResponseDropsMessagesContainingOnlyOpaqueContent()
    {
        // Arrange: one message with real text, one with only opaque AIContent
        ChatMessage usefulMessage = new(ChatRole.Assistant, "Hello, world!")
        {
            CreatedAt = DateTimeOffset.UtcNow
        };
        ChatMessage opaqueOnlyMessage = new(ChatRole.Assistant, [
            new AIContent
            {
                RawRepresentation = new { kind = "sessionEvent", sessionId = "s123" }
            }])
        {
            CreatedAt = DateTimeOffset.UtcNow.AddSeconds(1)
        };

        AgentResponse response = new(new List<ChatMessage> { usefulMessage, opaqueOnlyMessage })
        {
            CreatedAt = DateTimeOffset.UtcNow
        };

        // Act
        DurableAgentStateResponse durableResponse = DurableAgentStateResponse.FromResponse("corr-123", response);

        // Assert: only the useful message survives
        DurableAgentStateMessage durableMessage = Assert.Single(durableResponse.Messages);
        Assert.Equal(ChatRole.Assistant.Value, durableMessage.Role);

        // Round-trip to verify the content is correct
        AgentResponse convertedResponse = durableResponse.ToResponse();
        ChatMessage convertedMessage = Assert.Single(convertedResponse.Messages);
        TextContent textContent = Assert.IsType<TextContent>(Assert.Single(convertedMessage.Contents));
        Assert.Equal("Hello, world!", textContent.Text);
    }

    [Fact]
    public void FromResponseKeepsMessagesWithMixedContent()
    {
        // Arrange: one message with both real text and opaque AIContent
        ChatMessage mixedMessage = new(ChatRole.Assistant, [
            new TextContent("Some useful text"),
            new AIContent { RawRepresentation = new { kind = "metadata" } }])
        {
            CreatedAt = DateTimeOffset.UtcNow
        };

        AgentResponse response = new(new List<ChatMessage> { mixedMessage })
        {
            CreatedAt = DateTimeOffset.UtcNow
        };

        // Act
        DurableAgentStateResponse durableResponse = DurableAgentStateResponse.FromResponse("corr-456", response);

        // Assert: the message is kept because it contains at least one serializable content
        DurableAgentStateMessage durableMessage = Assert.Single(durableResponse.Messages);
        Assert.Equal(ChatRole.Assistant.Value, durableMessage.Role);
    }

    [Fact]
    public void FromResponseDropsAllMessagesWhenAllAreOpaque()
    {
        // Arrange: all messages contain only opaque AIContent
        ChatMessage opaque1 = new(ChatRole.Assistant, [
            new AIContent { RawRepresentation = new { kind = "event1" } }])
        {
            CreatedAt = DateTimeOffset.UtcNow
        };
        ChatMessage opaque2 = new(ChatRole.Assistant, [
            new AIContent { RawRepresentation = new { kind = "event2" } }])
        {
            CreatedAt = DateTimeOffset.UtcNow.AddSeconds(1)
        };

        AgentResponse response = new(new List<ChatMessage> { opaque1, opaque2 })
        {
            CreatedAt = DateTimeOffset.UtcNow
        };

        // Act
        DurableAgentStateResponse durableResponse = DurableAgentStateResponse.FromResponse("corr-789", response);

        // Assert: no messages stored
        Assert.Empty(durableResponse.Messages);
    }

    [Fact]
    public void FromResponseKeepsBaseAIContentWithAnnotations()
    {
        // Arrange: base AIContent with annotations should be kept
        AIContent contentWithAnnotations = new()
        {
            RawRepresentation = new { kind = "event" },
            Annotations = [new AIAnnotation() { AdditionalProperties = new() { ["cite"] = "ref-1" } }]
        };
        ChatMessage message = new(ChatRole.Assistant, [contentWithAnnotations])
        {
            CreatedAt = DateTimeOffset.UtcNow
        };

        AgentResponse response = new([message]) { CreatedAt = DateTimeOffset.UtcNow };

        // Act
        DurableAgentStateResponse durableResponse = DurableAgentStateResponse.FromResponse("corr-ann", response);

        // Assert: message is kept because the AIContent has annotations
        Assert.Single(durableResponse.Messages);
    }

    [Fact]
    public void FromResponseKeepsBaseAIContentWithAdditionalProperties()
    {
        // Arrange: base AIContent with additional properties should be kept
        AIContent contentWithProps = new()
        {
            RawRepresentation = new { kind = "event" },
            AdditionalProperties = new() { ["custom_key"] = "custom_value" }
        };
        ChatMessage message = new(ChatRole.Assistant, [contentWithProps])
        {
            CreatedAt = DateTimeOffset.UtcNow
        };

        AgentResponse response = new([message]) { CreatedAt = DateTimeOffset.UtcNow };

        // Act
        DurableAgentStateResponse durableResponse = DurableAgentStateResponse.FromResponse("corr-props", response);

        // Assert: message is kept because the AIContent has additional properties
        Assert.Single(durableResponse.Messages);
    }
}
