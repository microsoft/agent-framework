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
    public void ToA2APart_WithTextContent_ReturnsTextPart()
    {
        // Arrange
        var textContent = new TextContent("Hello, world!");

        // Act
        var result = textContent.ToA2APart();

        // Assert
        Assert.NotNull(result);

        var textPart = Assert.IsType<TextPart>(result);
        Assert.Equal("Hello, world!", textPart.Text);
    }

    [Fact]
    public void ToA2APart_WithHostedFileContent_ReturnsFilePart()
    {
        // Arrange
        const string Uri = "https://example.com/file.txt";
        var hostedFileContent = new HostedFileContent(Uri);

        // Act
        var result = hostedFileContent.ToA2APart();

        // Assert
        Assert.NotNull(result);

        var filePart = Assert.IsType<FilePart>(result);
        Assert.NotNull(filePart.File);

        var fileWithUri = Assert.IsType<FileWithUri>(filePart.File);
        Assert.Equal(Uri, fileWithUri.Uri);
    }

    [Fact]
    public void ToA2APart_WithUnsupportedContentType_ReturnsNull()
    {
        // Arrange
        var unsupportedContent = new MockAIContent();

        // Act
        var result = unsupportedContent.ToA2APart();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToA2AParts_WithEmptyCollection_ReturnsNull()
    {
        // Arrange
        var emptyContents = new List<AIContent>();

        // Act
        var result = emptyContents.ToA2AParts();

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
            new HostedFileContent("https://example.com/file1.txt"),
            new TextContent("Second text"),
            new HostedFileContent("https://example.com/file2.txt")
        };

        // Act
        var result = contents.ToA2AParts();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(4, result.Count);

        var firstTextPart = Assert.IsType<TextPart>(result[0]);
        Assert.Equal("First text", firstTextPart.Text);

        var firstFilePart = Assert.IsType<FilePart>(result[1]);
        var firstFileWithUri = Assert.IsType<FileWithUri>(firstFilePart.File);
        Assert.Equal("https://example.com/file1.txt", firstFileWithUri.Uri);

        var secondTextPart = Assert.IsType<TextPart>(result[2]);
        Assert.Equal("Second text", secondTextPart.Text);

        var secondFilePart = Assert.IsType<FilePart>(result[3]);
        var secondFileWithUri = Assert.IsType<FileWithUri>(secondFilePart.File);
        Assert.Equal("https://example.com/file2.txt", secondFileWithUri.Uri);
    }

    [Fact]
    public void ToA2AParts_WithMixedSupportedAndUnsupportedContent_IgnoresUnsupportedContent()
    {
        // Arrange
        var contents = new List<AIContent>
        {
            new TextContent("First text"),
            new MockAIContent(), // Unsupported - should be ignored
            new HostedFileContent("https://example.com/file.txt"),
            new MockAIContent(), // Unsupported - should be ignored
            new TextContent("Second text")
        };

        // Act
        var result = contents.ToA2AParts();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Count);

        var firstTextPart = Assert.IsType<TextPart>(result[0]);
        Assert.Equal("First text", firstTextPart.Text);

        var filePart = Assert.IsType<FilePart>(result[1]);
        var fileWithUri = Assert.IsType<FileWithUri>(filePart.File);
        Assert.Equal("https://example.com/file.txt", fileWithUri.Uri);

        var secondTextPart = Assert.IsType<TextPart>(result[2]);
        Assert.Equal("Second text", secondTextPart.Text);
    }

    // Mock class for testing unsupported scenarios
    private sealed class MockAIContent : AIContent;
}
