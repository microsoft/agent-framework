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

        Assert.Equal(PartContentCase.Text, result[0].ContentCase);
        Assert.Equal("First text", result[0].Text);

        Assert.Equal(PartContentCase.Url, result[1].ContentCase);
        Assert.Equal("https://example.com/file1.txt", result[1].Url);

        Assert.Equal(PartContentCase.Text, result[2].ContentCase);
        Assert.Equal("Second text", result[2].Text);
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

        Assert.Equal(PartContentCase.Text, result[0].ContentCase);
        Assert.Equal("First text", result[0].Text);

        Assert.Equal(PartContentCase.Url, result[1].ContentCase);
        Assert.Equal("https://example.com/file.txt", result[1].Url);

        Assert.Equal(PartContentCase.Text, result[2].ContentCase);
        Assert.Equal("Second text", result[2].Text);
    }

    // Mock class for testing unsupported scenarios
    private sealed class MockAIContent : AIContent;
}
