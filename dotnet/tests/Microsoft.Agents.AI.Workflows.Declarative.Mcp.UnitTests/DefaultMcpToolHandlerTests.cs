// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Protocol;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp.UnitTests;

/// <summary>
/// Unit tests for <see cref="DefaultMcpToolHandler"/>.
/// </summary>
public sealed class DefaultMcpToolHandlerTests
{
    [Fact]
    public void Constructor_WithNullHttpClientFactory_ShouldThrow()
    {
        // Act
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() => new DefaultMcpToolHandler(null!, "workflow-mcp"));

        // Assert
        Assert.Equal("httpClientFactory", exception.ParamName);
    }

    [Fact]
    public void Constructor_WithNullHttpClientName_ShouldThrow()
    {
        // Arrange
        Mock<IHttpClientFactory> factory = new();

        // Act
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() => new DefaultMcpToolHandler(factory.Object, null!));

        // Assert
        Assert.Equal("httpClientName", exception.ParamName);
    }

    [Theory]
    [InlineData("\r", false)]
    [InlineData("\n", false)]
    [InlineData("\0", false)]
    [InlineData("\r", true)]
    [InlineData("\n", true)]
    [InlineData("\0", true)]
    public async Task InvokeToolAsync_WithInvalidHeader_ShouldRejectBeforeClientCreationAsync(
        string invalidCharacter,
        bool invalidName)
    {
        // Arrange
        Mock<IHttpClientFactory> factory = new(MockBehavior.Strict);
        DefaultMcpToolHandler handler = new(factory.Object, "workflow-mcp");
        Dictionary<string, string> headers = new()
        {
            [invalidName ? $"X-Test{invalidCharacter}" : "X-Test"] = invalidName ? "value" : $"value{invalidCharacter}"
        };

        // Act
        ArgumentException exception = await Assert.ThrowsAsync<ArgumentException>(() => handler.InvokeToolAsync(
            "https://example.com/mcp", null, "ping", null, headers, null));

        // Assert
        Assert.Equal("headers", exception.ParamName);
        factory.Verify(f => f.CreateClient(It.IsAny<string>()), Times.Never);
    }

    [Fact]
    public async Task InvokeToolAsync_WithCancelledToken_ShouldRejectBeforeClientCreationAsync()
    {
        // Arrange
        Mock<IHttpClientFactory> factory = new(MockBehavior.Strict);
        DefaultMcpToolHandler handler = new(factory.Object, "workflow-mcp");
        using CancellationTokenSource cancellation = new();
        cancellation.Cancel();

        // Act
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => handler.InvokeToolAsync(
            "https://example.com/mcp", null, "ping", null, null, null, cancellation.Token));

        // Assert
        factory.Verify(f => f.CreateClient(It.IsAny<string>()), Times.Never);
    }

    #region Reserved Tools/List Tests

    [Fact]
    public void IsListToolsToolName_WithReservedName_ShouldReturnTrue()
    {
        // Act
        bool result = DefaultMcpToolHandler.IsListToolsToolName(DefaultMcpToolHandler.ListToolsToolName);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void IsListToolsToolName_WithRegularToolName_ShouldReturnFalse()
    {
        // Act
        bool result = DefaultMcpToolHandler.IsListToolsToolName("search");

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task InvokeToolAsync_WithListToolsArguments_ShouldThrowArgumentExceptionAsync()
    {
        // Arrange
        Mock<IHttpClientFactory> factory = new(MockBehavior.Strict);
        DefaultMcpToolHandler handler = new(factory.Object, "workflow-mcp");

        // Act
        ArgumentException exception = await Assert.ThrowsAsync<ArgumentException>(() => handler.InvokeToolAsync(
            "https://example.com/mcp", "test", DefaultMcpToolHandler.ListToolsToolName,
            new Dictionary<string, object?> { ["ignored"] = true }, null, null));

        // Assert
        Assert.Contains("does not accept tool arguments", exception.Message);
        factory.Verify(f => f.CreateClient(It.IsAny<string>()), Times.Never);
    }

    [Fact]
    public async Task CreateListToolsResultContent_WithTools_ShouldSerializeToolMetadataAsync()
    {
        // Arrange
        JsonElement inputSchema = JsonSerializer.Deserialize<JsonElement>(
            """
            {
              "type": "object",
              "properties": {
                "query": {
                  "type": "string"
                }
              },
              "required": [ "query" ]
            }
            """);
        Tool tool = new()
        {
            Name = "search",
            Description = "Searches documentation.",
            InputSchema = inputSchema
        };

        // Act
        McpServerToolResultContent result = DefaultMcpToolHandler.CreateListToolsResultContent([tool]);

        // Assert
        TextContent text = Assert.IsType<TextContent>(Assert.Single(result.Outputs ?? []));
        using JsonDocument document = JsonDocument.Parse(text.Text);
        JsonElement listedTool = document.RootElement.GetProperty("tools")[0];
        Assert.Equal("search", listedTool.GetProperty("name").GetString());
        Assert.Equal("Searches documentation.", listedTool.GetProperty("description").GetString());
        Assert.Equal("string", listedTool.GetProperty("inputSchema").GetProperty("properties").GetProperty("query").GetProperty("type").GetString());
    }

    #endregion

    #region ConvertContentBlock Tests

    [Fact]
    public void ConvertContentBlock_TextContentBlock_ShouldReturnTextContent()
    {
        // Arrange
        TextContentBlock block = new() { Text = "hello world" };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        TextContent textContent = Assert.IsType<TextContent>(result);
        Assert.Equal("hello world", textContent.Text);
        Assert.Same(block, textContent.RawRepresentation);
    }

    [Fact]
    public void ConvertContentBlock_ImageContentBlock_WithEmptyData_ShouldReturnDataContentWithEmptyUri()
    {
        // Arrange
        ImageContentBlock block = new() { Data = ReadOnlyMemory<byte>.Empty, MimeType = "image/png" };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.Equal("image/png", dataContent.MediaType);
        Assert.Equal("data:image/png;base64,", dataContent.Uri);
        Assert.True(dataContent.Data.IsEmpty);
        Assert.Same(block, dataContent.RawRepresentation);
    }

    [Fact]
    public void ConvertContentBlock_ImageContentBlock_WithBase64Payload_ShouldReturnDataContent()
    {
        // Arrange
        const string Base64Payload = "iVBORw0KGgo=";
        byte[] base64Bytes = Encoding.UTF8.GetBytes(Base64Payload);
        byte[] expectedDecoded = Convert.FromBase64String(Base64Payload);
        ImageContentBlock block = new() { Data = new ReadOnlyMemory<byte>(base64Bytes), MimeType = "image/png" };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.Equal("image/png", dataContent.MediaType);
        Assert.Equivalent(expectedDecoded, dataContent.Data.ToArray());
        Assert.Equal($"data:image/png;base64,{Base64Payload}", dataContent.Uri);
        Assert.Same(block, dataContent.RawRepresentation);
    }

    [Fact]
    public void ConvertContentBlock_AudioContentBlock_WithEmptyData_ShouldReturnDataContentWithEmptyUri()
    {
        // Arrange
        AudioContentBlock block = new() { Data = ReadOnlyMemory<byte>.Empty, MimeType = "audio/wav" };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.Equal("audio/wav", dataContent.MediaType);
        Assert.Equal("data:audio/wav;base64,", dataContent.Uri);
        Assert.True(dataContent.Data.IsEmpty);
        Assert.Same(block, dataContent.RawRepresentation);
    }

    [Fact]
    public void ConvertContentBlock_AudioContentBlock_WithBase64Payload_ShouldReturnDataContent()
    {
        // Arrange
        const string Base64Payload = "UklGRiQA";
        byte[] base64Bytes = Encoding.UTF8.GetBytes(Base64Payload);
        byte[] expectedDecoded = Convert.FromBase64String(Base64Payload);
        AudioContentBlock block = new() { Data = new ReadOnlyMemory<byte>(base64Bytes), MimeType = "audio/wav" };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.Equal("audio/wav", dataContent.MediaType);
        Assert.Equivalent(expectedDecoded, dataContent.Data.ToArray());
        Assert.Equal($"data:audio/wav;base64,{Base64Payload}", dataContent.Uri);
        Assert.Same(block, dataContent.RawRepresentation);
    }

    [Fact]
    public void ConvertContentBlock_EmbeddedResourceBlock_WithTextResource_ShouldReturnTextContent()
    {
        // Arrange
        EmbeddedResourceBlock block = new()
        {
            Resource = new TextResourceContents
            {
                Text = "embedded text payload",
                Uri = "resource://example",
                MimeType = "text/plain",
            },
        };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        TextContent textContent = Assert.IsType<TextContent>(result);
        Assert.Equal("embedded text payload", textContent.Text);
        Assert.Same(block, textContent.RawRepresentation);
    }

    [Fact]
    public void ConvertContentBlock_EmbeddedResourceBlock_WithBlobResource_ShouldReturnDataContent()
    {
        // Arrange
        const string Base64Payload = "UklGRiQA";
        byte[] base64Bytes = Encoding.UTF8.GetBytes(Base64Payload);
        byte[] expectedDecoded = Convert.FromBase64String(Base64Payload);
        EmbeddedResourceBlock block = new()
        {
            Resource = new BlobResourceContents
            {
                Blob = new ReadOnlyMemory<byte>(base64Bytes),
                Uri = "resource://example.bin",
                MimeType = "application/zip",
            },
        };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.Equal("application/zip", dataContent.MediaType);
        Assert.Equivalent(expectedDecoded, dataContent.Data.ToArray());
        Assert.Equal($"data:application/zip;base64,{Base64Payload}", dataContent.Uri);
        Assert.Same(block, dataContent.RawRepresentation);
    }

    [Fact]
    public void ConvertContentBlock_ResourceLinkBlock_WithUri_ShouldReturnUriContent()
    {
        // Arrange
        ResourceLinkBlock block = new()
        {
            Uri = "https://example.com/resource.bin",
            Name = "resource.bin",
            MimeType = "application/zip",
        };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        UriContent uriContent = Assert.IsType<UriContent>(result);
        Assert.Equal("https://example.com/resource.bin", uriContent.Uri.ToString());
        Assert.Equal("application/zip", uriContent.MediaType);
        Assert.Same(block, uriContent.RawRepresentation);
    }

    [Fact]
    public void ConvertContentBlock_ResourceLinkBlock_WithNullMimeType_ShouldDefaultToOctetStream()
    {
        // Arrange
        ResourceLinkBlock block = new()
        {
            Uri = "https://example.com/resource",
            Name = "resource",
            MimeType = null,
        };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        UriContent uriContent = Assert.IsType<UriContent>(result);
        Assert.Equal("https://example.com/resource", uriContent.Uri.ToString());
        Assert.Equal("application/octet-stream", uriContent.MediaType);
    }

    [Fact]
    public void ConvertContentBlock_ResourceLinkBlock_WithMeta_ShouldPropagateToAdditionalProperties()
    {
        // Arrange
        ResourceLinkBlock block = new()
        {
            Uri = "https://example.com/resource.bin",
            Name = string.Empty,
            MimeType = "application/zip",
            Meta = new System.Text.Json.Nodes.JsonObject
            {
                ["traceId"] = "abc-123",
                ["priority"] = 7,
            },
        };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        UriContent uriContent = Assert.IsType<UriContent>(result);
        Assert.NotNull(uriContent.AdditionalProperties);
        Assert.Equal(2, uriContent.AdditionalProperties.Count);
        Assert.Same(block.Meta!["traceId"], uriContent.AdditionalProperties["traceId"]);
        Assert.Same(block.Meta["priority"], uriContent.AdditionalProperties["priority"]);
    }

    [Fact]
    public void ConvertContentBlock_ResourceLinkBlock_WithName_ShouldMapNameToFilenameAdditionalProperty()
    {
        // Arrange
        ResourceLinkBlock block = new()
        {
            Uri = "https://example.com/resource.bin",
            Name = "resource.bin",
            MimeType = "application/zip",
        };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        UriContent uriContent = Assert.IsType<UriContent>(result);
        Assert.NotNull(uriContent.AdditionalProperties);
        Assert.Equal("resource.bin", uriContent.AdditionalProperties!["filename"]);
    }

#pragma warning disable MCP9005 // Verify compatibility mapping for deprecated sampling content blocks.
    [Fact]
    public void ConvertContentBlock_ToolUseContentBlock_ShouldReturnFunctionCallContent()
    {
        // Arrange
        using JsonDocument input = JsonDocument.Parse("{\"city\":\"Seattle\",\"unit\":\"celsius\"}");
        ToolUseContentBlock block = new()
        {
            Id = "call-1",
            Name = "get_weather",
            Input = input.RootElement.Clone(),
        };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        FunctionCallContent call = Assert.IsType<FunctionCallContent>(result);
        Assert.Equal("call-1", call.CallId);
        Assert.Equal("get_weather", call.Name);
        Assert.NotNull(call.Arguments);
        Assert.Contains("city", call.Arguments!);
        Assert.Same(block, call.RawRepresentation);
    }

    [Fact]
    public void ConvertContentBlock_ToolResultContentBlock_NotError_ShouldReturnFunctionResultContent()
    {
        // Arrange
        ToolResultContentBlock block = new()
        {
            ToolUseId = "call-1",
            Content = [new TextContentBlock { Text = "ok" }],
            IsError = false,
        };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        FunctionResultContent functionResult = Assert.IsType<FunctionResultContent>(result);
        Assert.Equal("call-1", functionResult.CallId);
        Assert.Null(functionResult.Exception);
        Assert.Same(block, functionResult.RawRepresentation);
    }

    [Fact]
    public void ConvertContentBlock_ToolResultContentBlock_WithIsError_ShouldSetException()
    {
        // Arrange
        ToolResultContentBlock block = new()
        {
            ToolUseId = "call-2",
            Content = [new TextContentBlock { Text = "boom" }],
            IsError = true,
        };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        FunctionResultContent functionResult = Assert.IsType<FunctionResultContent>(result);
        Assert.Equal("call-2", functionResult.CallId);
        Assert.NotNull(functionResult.Exception);
        Assert.Same(block, functionResult.RawRepresentation);
    }
#pragma warning restore MCP9005

    [Fact]
    public void ConvertContentBlock_BlockWithMeta_ShouldPropagateToAdditionalProperties()
    {
        // Arrange
        TextContentBlock block = new()
        {
            Text = "hello",
            Meta = new System.Text.Json.Nodes.JsonObject
            {
                ["traceId"] = "abc-123",
                ["priority"] = 7,
            },
        };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        Assert.NotNull(result.AdditionalProperties);
        Assert.True(result.AdditionalProperties!.ContainsKey("traceId"));
        Assert.True(result.AdditionalProperties.ContainsKey("priority"));
    }

    #endregion
}
