// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AMessageExtensions"/> class.
/// </summary>
public sealed class A2AMessageExtensionsTests
{
    [Fact]
    public void ToChatMessage_WithMixedParts_ReturnsChatMessageWithMixedContents()
    {
        // Arrange
        const string Uri = "https://example.com/image.jpg";

        var metadata = new Dictionary<string, JsonElement>
        {
            ["isUrgent"] = JsonDocument.Parse("true").RootElement
        };

        var message = new Message
        {
            MessageId = "mixed-parts-id",
            Role = MessageRole.Agent,
            Parts =
            [
                new TextPart { Text = "Here's an image:" },
                new FilePart { File = new FileWithUri { Uri = Uri } },
                new TextPart { Text = "What do you think?" }
            ],
            Metadata = metadata
        };

        // Act
        var result = message.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.Assistant, result.Role);
        Assert.Equal(message, result.RawRepresentation);

        Assert.NotNull(result.Contents);
        Assert.Equal(3, result.Contents.Count);

        var firstContent = Assert.IsType<TextContent>(result.Contents[0]);
        Assert.Equal("Here's an image:", firstContent.Text);

        var fileContent = Assert.IsType<HostedFileContent>(result.Contents[1]);
        Assert.Equal(Uri, fileContent.FileId);

        var lastContent = Assert.IsType<TextContent>(result.Contents[2]);
        Assert.Equal("What do you think?", lastContent.Text);

        Assert.NotNull(result.AdditionalProperties);
        Assert.Single(result.AdditionalProperties);

        Assert.True(result.AdditionalProperties.ContainsKey("isUrgent"));
        Assert.True(((JsonElement)result.AdditionalProperties["isUrgent"]!).GetBoolean());
    }
}
