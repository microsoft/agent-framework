// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIContentExtensions"/> class.
/// </summary>
public sealed class AIContentExtensionsTests
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
    public void ToA2APart_WithUnsupportedContentType_ThrowsNotSupportedException()
    {
        // Arrange
        var unsupportedContent = new MockAIContent();

        // Act & Assert
        var exception = Assert.Throws<NotSupportedException>(unsupportedContent.ToA2APart);
        Assert.Equal("Unsupported content type: MockAIContent.", exception.Message);
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

    // Mock class for testing unsupported scenarios
    private sealed class MockAIContent : AIContent;
}
