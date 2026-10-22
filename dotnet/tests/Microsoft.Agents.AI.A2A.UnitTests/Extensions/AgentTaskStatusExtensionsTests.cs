// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using A2A;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentTaskStatusExtensions"/> class.
/// </summary>
public sealed class AgentTaskStatusExtensionsTests
{
    [Fact]
    public void ToChatMessage_WithNullStatus_ThrowsArgumentNullException()
    {
        // Arrange
        TaskStatus status = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => status.ToChatMessage());
    }

    [Theory]
    [InlineData(TaskState.InputRequired)]
    [InlineData(TaskState.AuthRequired)]
    [InlineData(TaskState.Unspecified)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    [InlineData(TaskState.Rejected)]
    public void ToChatMessage_WithNullMessage_ReturnsNull(TaskState state)
    {
        // Arrange
        var status = new TaskStatus
        {
            State = state,
            Message = null,
        };

        // Act
        ChatMessage? result = status.ToChatMessage();

        // Assert
        Assert.Null(result);
    }

    [Theory]
    [InlineData(TaskState.Submitted)]
    [InlineData(TaskState.Working)]
    [InlineData(TaskState.Completed)]
    public void ToChatMessage_WithOtherStates_ReturnsNull(TaskState state)
    {
        // Arrange
        var status = new TaskStatus
        {
            State = state,
            Message = new Message { Parts = [Part.FromText("Some text")] },
        };

        // Act
        ChatMessage? result = status.ToChatMessage();

        // Assert
        Assert.Null(result);
    }

    [Theory]
    [InlineData(TaskState.InputRequired)]
    [InlineData(TaskState.AuthRequired)]
    [InlineData(TaskState.Unspecified)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    [InlineData(TaskState.Rejected)]
    public void ToChatMessage_WithStatusMessage_ReturnsStatusContents(TaskState state)
    {
        // Arrange
        var status = new TaskStatus
        {
            State = state,
            Message = new Message
            {
                Parts =
                [
                    Part.FromText("First request"),
                    Part.FromText("Second request"),
                    Part.FromText("Third request")
                ],
            },
        };

        // Act
        ChatMessage? result = status.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Contents.Count);
        Assert.Equal("First request", Assert.IsType<TextContent>(result.Contents[0]).Text);
        Assert.Equal("Second request", Assert.IsType<TextContent>(result.Contents[1]).Text);
        Assert.Equal("Third request", Assert.IsType<TextContent>(result.Contents[2]).Text);
    }

    [Theory]
    [InlineData(TaskState.InputRequired)]
    [InlineData(TaskState.AuthRequired)]
    [InlineData(TaskState.Unspecified)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    [InlineData(TaskState.Rejected)]
    public void ToChatMessage_WithTextParts_SetsRawRepresentationAndAdditionalPropertiesCorrectly(TaskState state)
    {
        // Arrange
        var textPart = Part.FromText("Input request");
        textPart.Metadata = new()
        {
            { "key1", JsonSerializer.SerializeToElement("value1") },
            { "key2", JsonSerializer.SerializeToElement("value2") }
        };
        var status = new TaskStatus
        {
            State = state,
            Message = new Message { Parts = [textPart] },
        };

        // Act
        ChatMessage? result = status.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        var content = Assert.IsType<TextContent>(result.Contents[0]);
        Assert.Same(textPart, content.RawRepresentation);
        Assert.NotNull(content.AdditionalProperties);
        Assert.Equal("value1", Assert.IsType<JsonElement>(content.AdditionalProperties["key1"]).GetString());
        Assert.Equal("value2", Assert.IsType<JsonElement>(content.AdditionalProperties["key2"]).GetString());
    }

    [Theory]
    [InlineData(TaskState.InputRequired)]
    [InlineData(TaskState.AuthRequired)]
    [InlineData(TaskState.Unspecified)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    [InlineData(TaskState.Rejected)]
    public void ToChatMessage_WithNonTextParts_PreservesContentAndMetadata(TaskState state)
    {
        // Arrange
        byte[] bytes = [1, 2, 3];
        var binaryPart = Part.FromRaw(bytes, "application/octet-stream");
        binaryPart.Filename = "details.bin";
        List<Part> parts =
        [
            Part.FromUrl("https://example.com/details.pdf", "application/pdf"),
            binaryPart,
            Part.FromData(JsonSerializer.SerializeToElement(new { action = "retry", retryable = true }))
        ];
        foreach (var part in parts)
        {
            part.Metadata = new() { ["part-key"] = JsonSerializer.SerializeToElement("part-value") };
        }

        var status = new TaskStatus
        {
            State = state,
            Message = new Message
            {
                Role = Role.Agent,
                MessageId = "status-message",
                Metadata = new() { ["reason"] = JsonSerializer.SerializeToElement(new { code = "needs-attention" }) },
                Parts = parts
            }
        };

        // Act
        var result = status.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.Assistant, result.Role);
        Assert.Equal("status-message", result.MessageId);
        Assert.Same(status.Message, result.RawRepresentation);
        Assert.NotNull(result.AdditionalProperties);
        Assert.Single(result.AdditionalProperties);
        Assert.Equal("needs-attention", Assert.IsType<JsonElement>(result.AdditionalProperties["reason"]).GetProperty("code").GetString());
        Assert.Equal(3, result.Contents.Count);

        var uriContent = Assert.IsType<UriContent>(result.Contents[0]);
        Assert.Equal(new Uri("https://example.com/details.pdf"), uriContent.Uri);
        Assert.Equal("application/pdf", uriContent.MediaType);
        var binaryContent = Assert.IsType<DataContent>(result.Contents[1]);
        Assert.Equal(bytes, binaryContent.Data.ToArray());
        Assert.Equal("details.bin", binaryContent.Name);
        Assert.Equal("application/octet-stream", binaryContent.MediaType);
        var jsonContent = Assert.IsType<DataContent>(result.Contents[2]);
        Assert.Equal("application/json", jsonContent.MediaType);
        using var data = JsonDocument.Parse(jsonContent.Data);
        Assert.Equal("retry", data.RootElement.GetProperty("action").GetString());
        Assert.True(data.RootElement.GetProperty("retryable").GetBoolean());

        for (int i = 0; i < parts.Count; i++)
        {
            Assert.Same(parts[i], result.Contents[i].RawRepresentation);
            var metadata = result.Contents[i].AdditionalProperties;
            Assert.NotNull(metadata);
            Assert.Single(metadata);
            Assert.Equal("part-value", Assert.IsType<JsonElement>(metadata["part-key"]).GetString());
        }
    }

    [Theory]
    [InlineData(TaskState.InputRequired)]
    [InlineData(TaskState.AuthRequired)]
    [InlineData(TaskState.Unspecified)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    [InlineData(TaskState.Rejected)]
    public void ToChatMessage_WithEmptyMessageParts_ReturnsNull(TaskState state)
    {
        // Arrange
        var status = new TaskStatus
        {
            State = state,
            Message = new Message { Parts = [] },
        };

        // Act
        ChatMessage? result = status.ToChatMessage();

        // Assert
        Assert.Null(result);
    }
}
