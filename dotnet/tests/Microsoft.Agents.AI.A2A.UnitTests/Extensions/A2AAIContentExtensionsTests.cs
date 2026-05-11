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

    [Fact]
    public void ToA2AParts_WithTextInputResponseContent_ReturnsTextPartWithResponse()
    {
        // Arrange
        var contents = new List<AIContent>
        {
            new A2AInputResponseContent("req-1", new TextContent("User input response"))
        };

        // Act
        var result = contents.ToParts();

        // Assert
        Assert.NotNull(result);
        Assert.Single(result);

        var textPart = result[0];
        Assert.Equal(PartContentCase.Text, textPart.ContentCase);
        Assert.Equal("User input response", textPart.Text);
    }

    [Fact]
    public void ToA2AParts_WithTextContentAndTextInputResponseContent_ReturnsMultipleParts()
    {
        // Arrange
        var contents = new List<AIContent>
        {
            new TextContent("Regular text"),
            new A2AInputResponseContent("req-1", new TextContent("User input response"))
        };

        // Act
        var result = contents.ToParts();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(2, result.Count);

        var firstPart = result[0];
        Assert.Equal(PartContentCase.Text, firstPart.ContentCase);
        Assert.Equal("Regular text", firstPart.Text);

        var secondPart = result[1];
        Assert.Equal(PartContentCase.Text, secondPart.ContentCase);
        Assert.Equal("User input response", secondPart.Text);
    }

    [Fact]
    public void ToA2AParts_WithMultipleTextInputResponseContents_ReturnsMultipleTextParts()
    {
        // Arrange
        var contents = new List<AIContent>
        {
            new A2AInputResponseContent("req-1", new TextContent("First response")),
            new A2AInputResponseContent("req-2", new TextContent("Second response")),
            new A2AInputResponseContent("req-3", new TextContent("Third response"))
        };

        // Act
        var result = contents.ToParts();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Count);

        var firstPart = result[0];
        Assert.Equal(PartContentCase.Text, firstPart.ContentCase);
        Assert.Equal("First response", firstPart.Text);

        var secondPart = result[1];
        Assert.Equal(PartContentCase.Text, secondPart.ContentCase);
        Assert.Equal("Second response", secondPart.Text);

        var thirdPart = result[2];
        Assert.Equal(PartContentCase.Text, thirdPart.ContentCase);
        Assert.Equal("Third response", thirdPart.Text);
    }

    [Fact]
    public void ToA2AParts_WithMixedContentAndTextInputResponseContent_ReturnsCorrectOrder()
    {
        // Arrange
        var contents = new List<AIContent>
        {
            new TextContent("Start"),
            new A2AInputResponseContent("req-1", new TextContent("Response")),
            new UriContent("https://example.com/file.txt", "file/txt"),
            new A2AInputResponseContent("req-2", new TextContent("Another response"))
        };

        // Act
        var result = contents.ToParts();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(4, result.Count);

        var firstPart = result[0];
        Assert.Equal(PartContentCase.Text, firstPart.ContentCase);
        Assert.Equal("Start", firstPart.Text);

        var secondPart = result[1];
        Assert.Equal(PartContentCase.Text, secondPart.ContentCase);
        Assert.Equal("Response", secondPart.Text);

        var thirdPart = result[2];
        Assert.Equal(PartContentCase.Url, thirdPart.ContentCase);
        Assert.Equal("https://example.com/file.txt", thirdPart.Url);

        var fourthPart = result[3];
        Assert.Equal(PartContentCase.Text, fourthPart.ContentCase);
        Assert.Equal("Another response", fourthPart.Text);
    }

    // Mock class for testing unsupported scenarios
    private sealed class MockAIContent : AIContent;
}
