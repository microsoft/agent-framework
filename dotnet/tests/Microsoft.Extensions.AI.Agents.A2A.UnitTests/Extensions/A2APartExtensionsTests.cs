// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2APartExtensions"/> class.
/// </summary>
public sealed class A2APartExtensionsTests
{
    [Fact]
    public void ToAIContent_WithTextPart_ReturnsTextContent()
    {
        // Arrange
        var textPart = new TextPart { Text = "Hello, world!" };

        // Act
        var result = textPart.ToAIContent();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(textPart, result.RawRepresentation);

        var textContent = Assert.IsType<TextContent>(result);
        Assert.Equal("Hello, world!", textContent.Text);
    }

    [Fact]
    public void ToAIContent_WithTextPartWithMetadata_ReturnsTextContentWithAdditionalProperties()
    {
        // Arrange
        var metadata = new Dictionary<string, JsonElement>
        {
            ["key1"] = JsonDocument.Parse("\"value1\"").RootElement,
            ["key2"] = JsonDocument.Parse("42").RootElement,
            ["key3"] = JsonDocument.Parse("true").RootElement
        };
        var textPart = new TextPart
        {
            Text = "Hello with metadata!",
            Metadata = metadata
        };

        // Act
        var result = textPart.ToAIContent();

        // Assert
        Assert.NotNull(result);
        var textContent = Assert.IsType<TextContent>(result);
        Assert.Equal("Hello with metadata!", textContent.Text);
        Assert.NotNull(textContent.AdditionalProperties);
        Assert.Equal(3, textContent.AdditionalProperties.Count);
        Assert.True(textContent.AdditionalProperties.ContainsKey("key1"));
        Assert.True(textContent.AdditionalProperties.ContainsKey("key2"));
        Assert.True(textContent.AdditionalProperties.ContainsKey("key3"));
    }

    [Fact]
    public void ToAIContent_WithFilePartWithFileWithUri_ReturnsHostedFileContent()
    {
        // Arrange
        const string Uri = "https://example.com/file.txt";
        var filePart = new FilePart { File = new FileWithUri { Uri = Uri } };

        // Act
        var result = filePart.ToAIContent();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(filePart, result.RawRepresentation);

        var hostedFileContent = Assert.IsType<HostedFileContent>(result);
        Assert.Equal(Uri, hostedFileContent.FileId);
        Assert.Null(hostedFileContent.AdditionalProperties);
    }

    [Fact]
    public void ToAIContent_WithCustomPartType_ThrowsNotSupportedException()
    {
        // Arrange
        var customPart = new MockPart();

        // Act & Assert
        var exception = Assert.Throws<NotSupportedException>(customPart.ToAIContent);
        Assert.Equal("Part type 'MockPart' is not supported.", exception.Message);
    }

    // Mock class for testing unsupported scenarios
    private sealed class MockPart : Part;
}
