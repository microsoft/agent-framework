// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for MessageContentPartConverter focusing on MIME type handling for image URIs.
/// </summary>
public sealed class MessageContentPartConverterTests
{
    [Theory]
    [InlineData("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "image/png")]
    [InlineData("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlbaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD5/ooooA//2Q==", "image/jpeg")]
    [InlineData("data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==", "image/gif")]
    [InlineData("data:image/webp;base64,UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAgA0JaQAA3AA/vuUAAA=", "image/webp")]
    [InlineData("data:image/bmp;base64,Qk0eAAAAAAAAABoAAAAMAAAAAQAAAAEAAAABACAAAAA=", "image/bmp")]
    public void ToAIContent_ImageDataUri_PreservesMimeType(string dataUri, string expectedMediaType)
    {
        // Arrange
        ImageContentPart imagePart = new ImageContentPart
        {
            ImageUrl = new ImageUrl { Url = dataUri }
        };

        // Act
        AIContent? result = MessageContentPartConverter.ToAIContent(imagePart);

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
    public void ToAIContent_ImageHttpUri_InfersMimeTypeFromExtension(string uri, string expectedMediaType)
    {
        // Arrange
        ImageContentPart imagePart = new ImageContentPart
        {
            ImageUrl = new ImageUrl { Url = uri }
        };

        // Act
        AIContent? result = MessageContentPartConverter.ToAIContent(imagePart);

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
    public void ToAIContent_ImageHttpUri_UnknownExtension_UsesGenericMimeType(string uri)
    {
        // Arrange
        ImageContentPart imagePart = new ImageContentPart
        {
            ImageUrl = new ImageUrl { Url = uri }
        };

        // Act
        AIContent? result = MessageContentPartConverter.ToAIContent(imagePart);

        // Assert
        Assert.NotNull(result);
        UriContent uriContent = Assert.IsType<UriContent>(result);
        Assert.Equal("image/*", uriContent.MediaType);
        Assert.Equal(uri, uriContent.Uri?.ToString());
    }

    [Fact]
    public void ToAIContent_ImageDataUriPng_CreatesDataContent()
    {
        // Arrange
        const string dataUri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";
        ImageContentPart imagePart = new ImageContentPart
        {
            ImageUrl = new ImageUrl { Url = dataUri }
        };

        // Act
        AIContent? result = MessageContentPartConverter.ToAIContent(imagePart);

        // Assert
        Assert.NotNull(result);
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.Equal("image/png", dataContent.MediaType);
        Assert.Equal(dataUri, dataContent.Uri);
    }

    [Fact]
    public void ToAIContent_ImageHttpUriPng_CreatesUriContent()
    {
        // Arrange
        const string uri = "https://example.com/test.png";
        ImageContentPart imagePart = new ImageContentPart
        {
            ImageUrl = new ImageUrl { Url = uri }
        };

        // Act
        AIContent? result = MessageContentPartConverter.ToAIContent(imagePart);

        // Assert
        Assert.NotNull(result);
        UriContent uriContent = Assert.IsType<UriContent>(result);
        Assert.Equal("image/png", uriContent.MediaType);
        Assert.Equal(uri, uriContent.Uri?.ToString());
    }

    [Fact]
    public void ToAIContent_TextPart_CreatesTextContent()
    {
        // Arrange
        const string text = "Hello, world!";
        TextContentPart textPart = new TextContentPart
        {
            Text = text
        };

        // Act
        AIContent? result = MessageContentPartConverter.ToAIContent(textPart);

        // Assert
        Assert.NotNull(result);
        TextContent textContent = Assert.IsType<TextContent>(result);
        Assert.Equal(text, textContent.Text);
    }

    [Fact]
    public void ToAIContent_EmptyImageUrl_ReturnsNull()
    {
        // Arrange
        ImageContentPart imagePart = new ImageContentPart
        {
            ImageUrl = new ImageUrl { Url = string.Empty }
        };

        // Act
        AIContent? result = MessageContentPartConverter.ToAIContent(imagePart);

        // Assert
        Assert.Null(result);
    }

    [Theory]
    [InlineData("mp3", "audio/mpeg")]
    [InlineData("wav", "audio/wav")]
    [InlineData("opus", "audio/opus")]
    [InlineData("aac", "audio/aac")]
    [InlineData("flac", "audio/flac")]
    [InlineData("pcm16", "audio/pcm")]
    public void ToAIContent_AudioPart_CorrectMimeType(string format, string expectedMediaType)
    {
        // Arrange
        const string audioData = "data:audio/wav;base64,UklGRiQAAABXQVZF";
        AudioContentPart audioPart = new AudioContentPart
        {
            InputAudio = new InputAudio
            {
                Data = audioData,
                Format = format
            }
        };

        // Act
        AIContent? result = MessageContentPartConverter.ToAIContent(audioPart);

        // Assert
        Assert.NotNull(result);
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.Equal(expectedMediaType, dataContent.MediaType);
    }

    [Fact]
    public void ToAIContent_FilePartWithFileId_CreatesHostedFileContent()
    {
        // Arrange
        const string fileId = "file-abc123";
        FileContentPart filePart = new FileContentPart
        {
            File = new InputFile { FileId = fileId }
        };

        // Act
        AIContent? result = MessageContentPartConverter.ToAIContent(filePart);

        // Assert
        Assert.NotNull(result);
        HostedFileContent hostedFile = Assert.IsType<HostedFileContent>(result);
        Assert.Equal(fileId, hostedFile.FileId);
    }

    [Fact]
    public void ToAIContent_FilePartWithFileData_CreatesDataContent()
    {
        // Arrange
        const string fileData = "data:application/pdf;base64,JVBERi0xLjQ=";
        const string filename = "document.pdf";
        FileContentPart filePart = new FileContentPart
        {
            File = new InputFile
            {
                FileData = fileData,
                Filename = filename
            }
        };

        // Act
        AIContent? result = MessageContentPartConverter.ToAIContent(filePart);

        // Assert
        Assert.NotNull(result);
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.Equal("application/octet-stream", dataContent.MediaType);
        Assert.Equal(filename, dataContent.Name);
    }
}
