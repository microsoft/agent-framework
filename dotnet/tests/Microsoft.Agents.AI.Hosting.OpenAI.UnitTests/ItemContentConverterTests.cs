// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for ItemContentConverter focusing on MIME type handling for image URIs.
/// </summary>
public sealed class ItemContentConverterTests
{
    [Theory]
    [InlineData("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "image/png")]
    [InlineData("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlbaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD5/ooooA//2Q==", "image/jpeg")]
    [InlineData("data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==", "image/gif")]
    [InlineData("data:image/webp;base64,UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAgA0JaQAA3AA/vuUAAA=", "image/webp")]
    [InlineData("data:image/bmp;base64,Qk0eAAAAAAAAABoAAAAMAAAAAQAAAAEAAAABACAAAAA=", "image/bmp")]
    public void ToAIContent_DataUri_PreservesMimeType(string dataUri, string expectedMediaType)
    {
        // Arrange
        ItemContentInputImage inputImage = new ItemContentInputImage
        {
            ImageUrl = dataUri
        };

        // Act
        AIContent? result = ItemContentConverter.ToAIContent(inputImage);

        // Assert
        Assert.NotNull(result);
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.Equal(expectedMediaType, dataContent.MediaType);
        Assert.Equal(dataUri, dataContent.Uri);
    }

    [Theory]
    [InlineData("https://example.com/image.png", "image/png")]
    [InlineData("https://example.com/photo.jpg", "image/jpeg")]
    [InlineData("https://example.com/photo.jpeg", "image/jpeg")]
    [InlineData("https://example.com/animation.gif", "image/gif")]
    [InlineData("https://example.com/picture.bmp", "image/bmp")]
    [InlineData("https://example.com/modern.webp", "image/webp")]
    [InlineData("https://example.com/IMAGE.PNG", "image/png")] // Case insensitive
    [InlineData("https://example.com/PHOTO.JPG", "image/jpeg")] // Case insensitive
    public void ToAIContent_HttpUri_InfersMimeTypeFromExtension(string uri, string expectedMediaType)
    {
        // Arrange
        ItemContentInputImage inputImage = new ItemContentInputImage
        {
            ImageUrl = uri
        };

        // Act
        AIContent? result = ItemContentConverter.ToAIContent(inputImage);

        // Assert
        Assert.NotNull(result);
        UriContent uriContent = Assert.IsType<UriContent>(result);
        Assert.Equal(expectedMediaType, uriContent.MediaType);
        Assert.Equal(uri, uriContent.Uri?.ToString());
    }

    [Theory]
    [InlineData("https://example.com/image")]
    [InlineData("https://example.com/image.unknown")]
    [InlineData("https://example.com/image.txt")]
    public void ToAIContent_HttpUri_UnknownExtension_UsesGenericMimeType(string uri)
    {
        // Arrange
        ItemContentInputImage inputImage = new ItemContentInputImage
        {
            ImageUrl = uri
        };

        // Act
        AIContent? result = ItemContentConverter.ToAIContent(inputImage);

        // Assert
        Assert.NotNull(result);
        UriContent uriContent = Assert.IsType<UriContent>(result);
        Assert.Equal("image/*", uriContent.MediaType);
        Assert.Equal(uri, uriContent.Uri?.ToString());
    }

    [Fact]
    public void ToAIContent_DataUriPng_CreatesDataContent()
    {
        // Arrange
        const string dataUri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";
        ItemContentInputImage inputImage = new ItemContentInputImage
        {
            ImageUrl = dataUri
        };

        // Act
        AIContent? result = ItemContentConverter.ToAIContent(inputImage);

        // Assert
        Assert.NotNull(result);
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.Equal("image/png", dataContent.MediaType);
        Assert.Equal(dataUri, dataContent.Uri);
    }

    [Fact]
    public void ToAIContent_HttpUriPng_CreatesUriContent()
    {
        // Arrange
        const string uri = "https://example.com/test.png";
        ItemContentInputImage inputImage = new ItemContentInputImage
        {
            ImageUrl = uri
        };

        // Act
        AIContent? result = ItemContentConverter.ToAIContent(inputImage);

        // Assert
        Assert.NotNull(result);
        UriContent uriContent = Assert.IsType<UriContent>(result);
        Assert.Equal("image/png", uriContent.MediaType);
        Assert.Equal(uri, uriContent.Uri?.ToString());
    }

    [Fact]
    public void ToAIContent_FileId_CreatesHostedFileContent()
    {
        // Arrange
        const string fileId = "file-abc123";
        ItemContentInputImage inputImage = new ItemContentInputImage
        {
            FileId = fileId
        };

        // Act
        AIContent? result = ItemContentConverter.ToAIContent(inputImage);

        // Assert
        Assert.NotNull(result);
        HostedFileContent hostedFile = Assert.IsType<HostedFileContent>(result);
        Assert.Equal(fileId, hostedFile.FileId);
    }

    [Fact]
    public void ToAIContent_NullImageUrl_ReturnsNull()
    {
        // Arrange
        ItemContentInputImage inputImage = new ItemContentInputImage
        {
            ImageUrl = null
        };

        // Act
        AIContent? result = ItemContentConverter.ToAIContent(inputImage);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToAIContent_EmptyImageUrl_ReturnsNull()
    {
        // Arrange
        ItemContentInputImage inputImage = new ItemContentInputImage
        {
            ImageUrl = string.Empty
        };

        // Act
        AIContent? result = ItemContentConverter.ToAIContent(inputImage);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToAIContent_PreservesImageDetail()
    {
        // Arrange
        const string uri = "https://example.com/test.png";
        ItemContentInputImage inputImage = new ItemContentInputImage
        {
            ImageUrl = uri,
            Detail = "high"
        };

        // Act
        AIContent? result = ItemContentConverter.ToAIContent(inputImage);

        // Assert
        Assert.NotNull(result);
        UriContent uriContent = Assert.IsType<UriContent>(result);
        Assert.NotNull(uriContent.AdditionalProperties);
        Assert.True(uriContent.AdditionalProperties.TryGetValue("detail", out object? detail));
        Assert.Equal("high", detail?.ToString());
    }
}
