// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.DurableTask.State;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.Tests.Unit.State;

public sealed class DurableAgentStateMessageTests
{
    [Fact]
    public void MessageSerializationDeserialization()
    {
        // Arrange
        TextContent textContent = new("Hello, world!");
        ChatMessage message = new(ChatRole.User, [textContent])
        {
            AuthorName = "User123",
            CreatedAt = DateTimeOffset.UtcNow
        };

        DurableAgentStateMessage durableMessage = DurableAgentStateMessage.FromChatMessage(message);

        // Act
        string jsonContent = JsonSerializer.Serialize(
            durableMessage,
            DurableAgentStateJsonContext.Default.GetTypeInfo(typeof(DurableAgentStateMessage))!);

        DurableAgentStateMessage? convertedJsonContent = (DurableAgentStateMessage?)JsonSerializer.Deserialize(
            jsonContent,
            DurableAgentStateJsonContext.Default.GetTypeInfo(typeof(DurableAgentStateMessage))!);

        // Assert
        Assert.NotNull(convertedJsonContent);

        ChatMessage convertedMessage = convertedJsonContent.ToChatMessage();

        Assert.Equal(message.AuthorName, convertedMessage.AuthorName);
        Assert.Equal(message.CreatedAt, convertedMessage.CreatedAt);
        Assert.Equal(message.Role, convertedMessage.Role);

        AIContent convertedContent = Assert.Single(convertedMessage.Contents);
        TextContent convertedTextContent = Assert.IsType<TextContent>(convertedContent);

        Assert.Equal(textContent.Text, convertedTextContent.Text);
    }
}
