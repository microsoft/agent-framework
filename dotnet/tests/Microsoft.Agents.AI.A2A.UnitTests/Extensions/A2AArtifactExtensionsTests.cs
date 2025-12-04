// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using A2A;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AArtifactExtensions"/> class.
/// </summary>
public sealed class A2AArtifactExtensionsTests
{
    [Fact]
    public void ToChatMessage_WithMultiplePartsMetadataAndRawRepresentation_ReturnsCorrectChatMessage()
    {
        // Arrange
        var artifact = new Artifact
        {
            ArtifactId = "artifact-comprehensive",
            Name = "comprehensive-artifact",
            Parts =
            [
                new TextPart { Text = "First part" },
                new TextPart { Text = "Second part" },
                new TextPart { Text = "Third part" }
            ],
            Metadata = new Dictionary<string, JsonElement>
            {
                { "key1", JsonSerializer.SerializeToElement("value1") },
                { "key2", JsonSerializer.SerializeToElement(42) }
            }
        };

        // Act
        var result = artifact.ToChatMessage();

        // Assert - Verify multiple parts
        Assert.NotNull(result);
        Assert.Equal(ChatRole.Assistant, result.Role);
        Assert.Equal(3, result.Contents.Count);
        Assert.All(result.Contents, content => Assert.IsType<TextContent>(content));
        Assert.Equal("First part", ((TextContent)result.Contents[0]).Text);
        Assert.Equal("Second part", ((TextContent)result.Contents[1]).Text);
        Assert.Equal("Third part", ((TextContent)result.Contents[2]).Text);

        // Assert - Verify metadata conversion to AdditionalProperties
        Assert.NotNull(result.AdditionalProperties);
        Assert.Equal(2, result.AdditionalProperties.Count);
        Assert.True(result.AdditionalProperties.ContainsKey("key1"));
        Assert.True(result.AdditionalProperties.ContainsKey("key2"));

        // Assert - Verify RawRepresentation is set to artifact
        Assert.NotNull(result.RawRepresentation);
        Assert.Same(artifact, result.RawRepresentation);
    }

    [Fact]
    public void ToAIContents_WithMultipleParts_ReturnsCorrectList()
    {
        // Arrange
        var artifact = new Artifact
        {
            ArtifactId = "artifact-ai-multi",
            Name = "test",
            Parts = new List<Part>
            {
                new TextPart { Text = "Part 1" },
                new TextPart { Text = "Part 2" },
                new TextPart { Text = "Part 3" }
            },
            Metadata = null
        };

        // Act
        var result = artifact.ToAIContents();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Count);
        Assert.All(result, content => Assert.IsType<TextContent>(content));
        Assert.Equal("Part 1", ((TextContent)result[0]).Text);
        Assert.Equal("Part 2", ((TextContent)result[1]).Text);
        Assert.Equal("Part 3", ((TextContent)result[2]).Text);
    }

    [Fact]
    public void ToAIContents_WithEmptyParts_ReturnsEmptyList()
    {
        // Arrange
        var artifact = new Artifact
        {
            ArtifactId = "artifact-empty",
            Name = "test",
            Parts = new List<Part>(),
            Metadata = null
        };

        // Act
        var result = artifact.ToAIContents();

        // Assert
        Assert.NotNull(result);
        Assert.Empty(result);
    }
}
