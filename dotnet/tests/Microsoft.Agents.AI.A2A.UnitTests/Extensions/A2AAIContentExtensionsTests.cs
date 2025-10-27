// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using A2A;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AAIContentExtensions"/> class.
/// </summary>
public sealed class A2AAIContentExtensionsTests
{
    [Fact]
    public void ToA2AParts_WithEmptyCollection_ReturnsNull()
    {
        // Arrange
        var emptyContents = new List<AIContent>();

        // Act
        var result = emptyContents.ToParts();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToA2AParts_WithMultipleContents_ReturnsListWithAllParts()
    {
        // Arrange
        var contents = new List<AIContent>
        {
            new TextContent("First text"),
            new UriContent("https://example.com/file1.txt", "file/txt"),
            new TextContent("Second text"),
        };

        // Act
        var result = contents.ToParts();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Count);

        var firstTextPart = Assert.IsType<TextPart>(result[0]);
        Assert.Equal("First text", firstTextPart.Text);

        var filePart = Assert.IsType<FilePart>(result[1]);
        Assert.Equal("https://example.com/file1.txt", filePart.File.Uri?.ToString());

        var secondTextPart = Assert.IsType<TextPart>(result[2]);
        Assert.Equal("Second text", secondTextPart.Text);
    }

    [Fact]
    public void ToA2AParts_WithMixedSupportedAndUnsupportedContent_IgnoresUnsupportedContent()
    {
        // Arrange
        var contents = new List<AIContent>
        {
            new TextContent("First text"),
            new MockAIContent(), // Unsupported - should be ignored
            new UriContent("https://example.com/file.txt", "file/txt"),
            new MockAIContent(), // Unsupported - should be ignored
            new TextContent("Second text")
        };

        // Act
        var result = contents.ToParts();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Count);

        var firstTextPart = Assert.IsType<TextPart>(result[0]);
        Assert.Equal("First text", firstTextPart.Text);

        var filePart = Assert.IsType<FilePart>(result[1]);
        Assert.Equal("https://example.com/file.txt", filePart.File.Uri?.ToString());

        var secondTextPart = Assert.IsType<TextPart>(result[2]);
        Assert.Equal("Second text", secondTextPart.Text);
    }

    // Mock class for testing unsupported scenarios
    private sealed class MockAIContent : AIContent;
}
