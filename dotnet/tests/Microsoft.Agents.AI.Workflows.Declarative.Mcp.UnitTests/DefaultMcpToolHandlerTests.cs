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

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp.UnitTests;

/// <summary>
/// Unit tests for <see cref="DefaultMcpToolHandler"/>.
/// </summary>
public sealed class DefaultMcpToolHandlerTests
{
    #region Constructor Tests

    [Fact]
    public async Task Constructor_WithNoParameters_ShouldCreateInstanceAsync()
    {
        // Act
        DefaultMcpToolHandler handler = new();

        // Assert
        Assert.NotNull(handler);
        await handler.DisposeAsync();
    }

    [Fact]
    public async Task Constructor_WithNullHttpClientProvider_ShouldCreateInstanceAsync()
    {
        // Act
        DefaultMcpToolHandler handler = new(null);

        // Assert
        Assert.NotNull(handler);
        await handler.DisposeAsync();
    }

    [Fact]
    public async Task Constructor_WithHttpClientProvider_ShouldCreateInstanceAsync()
    {
        // Arrange
        static Task<HttpClient?> ProviderAsync(string url, CancellationToken ct) => Task.FromResult<HttpClient?>(new HttpClient());

        // Act
        DefaultMcpToolHandler handler = new(httpClientProvider: ProviderAsync);

        // Assert
        Assert.NotNull(handler);
        await handler.DisposeAsync();
    }

    #endregion

    #region DisposeAsync Tests

    [Fact]
    public async Task DisposeAsync_WhenCalled_ShouldCompleteWithoutErrorAsync()
    {
        // Arrange
        DefaultMcpToolHandler handler = new();

        // Act
        async Task actAsync() => await handler.DisposeAsync();

        // Assert
        Assert.Null(await Record.ExceptionAsync(actAsync));
    }

    [Fact]
    public async Task DisposeAsync_WhenCalledMultipleTimes_ShouldHandleGracefullyAsync()
    {
        // Arrange
        DefaultMcpToolHandler handler = new();

        // Act
        await handler.DisposeAsync();
        async Task actAsync() => await handler.DisposeAsync();

        // Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(actAsync);
    }

    #endregion

    #region HttpClientProvider Tests

    [Theory]
    [InlineData("\r", false, false)]
    [InlineData("\n", false, false)]
    [InlineData("\0", false, false)]
    [InlineData("\r", true, false)]
    [InlineData("\n", true, false)]
    [InlineData("\0", true, false)]
    [InlineData("\r", false, true)]
    [InlineData("\n", false, true)]
    [InlineData("\0", false, true)]
    [InlineData("\r", true, true)]
    [InlineData("\n", true, true)]
    [InlineData("\0", true, true)]
    public async Task InvokeToolAsync_WithInvalidHeader_ShouldRejectBeforeClientCreationAsync(
        string invalidCharacter,
        bool invalidName,
        bool useProvider)
    {
        // Arrange
        bool clientCreationAttempted = false;
        Task<HttpClient?> ProviderAsync(string url, CancellationToken ct)
        {
            clientCreationAttempted = true;
            throw new InvalidOperationException("Client creation should not be reached.");
        }

        HttpMessageHandler CreateHandler()
        {
            clientCreationAttempted = true;
            throw new InvalidOperationException("Client creation should not be reached.");
        }

        await using DefaultMcpToolHandler handler = new(useProvider ? ProviderAsync : null, CreateHandler);
        Dictionary<string, string> headers = new()
        {
            [invalidName ? $"X-Test{invalidCharacter}" : "X-Test"] = invalidName ? "value" : $"value{invalidCharacter}"
        };

        // Act
        async Task actAsync() => await handler.InvokeToolAsync(
            serverUrl: "https://example.com/mcp",
            serverLabel: null,
            toolName: "testTool",
            arguments: null,
            headers: headers,
            connectionName: null);

        // Assert
        ArgumentException exception = await Assert.ThrowsAsync<ArgumentException>(actAsync);
        Assert.Equal("headers", exception.ParamName);
        Assert.False(clientCreationAttempted);
    }

    [Fact]
    public async Task InvokeToolAsync_WithHttpClientProvider_ShouldCallProviderAsync()
    {
        // Arrange
        bool providerCalled = false;
        string? capturedServerUrl = null;

        Task<HttpClient?> ProviderAsync(string url, CancellationToken ct)
        {
            providerCalled = true;
            capturedServerUrl = url;
            return Task.FromResult<HttpClient?>(null);
        }

        DefaultMcpToolHandler handler = new(httpClientProvider: ProviderAsync);

        // Act & Assert - The call will fail because there's no real MCP server, but the provider should be called
        try
        {
            await handler.InvokeToolAsync(
                serverUrl: "http://localhost:12345/mcp",
                serverLabel: "test",
                toolName: "testTool",
                arguments: null,
                headers: null,
                connectionName: null);
        }
        catch
        {
            // Expected to fail - no real server
        }
        finally
        {
            await handler.DisposeAsync();
        }

        // Assert
        Assert.True(providerCalled);
        Assert.Equal("http://localhost:12345/mcp", capturedServerUrl);
    }

    [Fact]
    public async Task InvokeToolAsync_WithHttpClientProviderReturningClient_ShouldUseProvidedClientAsync()
    {
        // Arrange
        bool providerCalled = false;
        HttpClient? providedClient = null;

        Task<HttpClient?> ProviderAsync(string url, CancellationToken ct)
        {
            providerCalled = true;
            providedClient = new HttpClient();
            return Task.FromResult<HttpClient?>(providedClient);
        }

        DefaultMcpToolHandler handler = new(httpClientProvider: ProviderAsync);

        // Act & Assert - The call will fail because there's no real MCP server, but the provider should be called
        try
        {
            await handler.InvokeToolAsync(
                serverUrl: "http://localhost:12345/mcp",
                serverLabel: "test",
                toolName: "testTool",
                arguments: null,
                headers: null,
                connectionName: null);
        }
        catch
        {
            // Expected to fail - no real server
        }
        finally
        {
            await handler.DisposeAsync();
            providedClient?.Dispose();
        }

        // Assert
        Assert.True(providerCalled);
    }

    #endregion

    #region Invocation Tests

    [Fact]
    public async Task InvokeToolAsync_SameServerUrl_ShouldCallProviderOncePerAttemptWhenConnectionFailsAsync()
    {
        // Arrange
        int providerCallCount = 0;

        Task<HttpClient?> ProviderAsync(string url, CancellationToken ct)
        {
            providerCallCount++;
            return Task.FromResult<HttpClient?>(null);
        }

        DefaultMcpToolHandler handler = new(httpClientProvider: ProviderAsync);
        const string ServerUrl = "http://localhost:12345/mcp";

        try
        {
            // Act - Call twice with the same server URL
            for (int i = 0; i < 2; i++)
            {
                try
                {
                    await handler.InvokeToolAsync(
                        serverUrl: ServerUrl,
                        serverLabel: "test",
                        toolName: "testTool",
                        arguments: null,
                        headers: null,
                        connectionName: null);
                }
                catch
                {
                    // Expected to fail - no real server
                }
            }

            // Assert
            Assert.Equal(2, providerCallCount);
        }
        finally
        {
            await handler.DisposeAsync();
        }
    }

    [Fact]
    public async Task InvokeToolAsync_DifferentServerUrls_ShouldCreateSeparateClientsAsync()
    {
        // Arrange
        int providerCallCount = 0;

        Task<HttpClient?> ProviderAsync(string url, CancellationToken ct)
        {
            providerCallCount++;
            return Task.FromResult<HttpClient?>(null);
        }

        DefaultMcpToolHandler handler = new(httpClientProvider: ProviderAsync);

        try
        {
            // Act - Call with different server URLs
            foreach (string serverUrl in new[] { "http://localhost:12345/mcp1", "http://localhost:12345/mcp2" })
            {
                try
                {
                    await handler.InvokeToolAsync(
                        serverUrl: serverUrl,
                        serverLabel: "test",
                        toolName: "testTool",
                        arguments: null,
                        headers: null,
                        connectionName: null);
                }
                catch
                {
                    // Expected to fail - no real server
                }
            }

            // Assert - Provider should be called once per unique server URL
            Assert.Equal(2, providerCallCount);
        }
        finally
        {
            await handler.DisposeAsync();
        }
    }

    [Fact]
    public async Task InvokeToolAsync_SameUrlDifferentHeaders_ShouldCreateSeparateClientsAsync()
    {
        // Arrange
        int providerCallCount = 0;

        Task<HttpClient?> ProviderAsync(string url, CancellationToken ct)
        {
            providerCallCount++;
            return Task.FromResult<HttpClient?>(null);
        }

        DefaultMcpToolHandler handler = new(httpClientProvider: ProviderAsync);
        const string ServerUrl = "http://localhost:12345/mcp";

        try
        {
            // Act - Call with same URL but different headers
            Dictionary<string, string>[] headerSets =
            [
                new() { ["Authorization"] = "Bearer token1" },
                new() { ["Authorization"] = "Bearer token2" }
            ];

            foreach (Dictionary<string, string> headers in headerSets)
            {
                try
                {
                    await handler.InvokeToolAsync(
                        serverUrl: ServerUrl,
                        serverLabel: "test",
                        toolName: "testTool",
                        arguments: null,
                        headers: headers,
                        connectionName: null);
                }
                catch
                {
                    // Expected to fail - no real server
                }
            }

            // Assert
            Assert.Equal(2, providerCallCount);
        }
        finally
        {
            await handler.DisposeAsync();
        }
    }

    #endregion

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
        DefaultMcpToolHandler handler = new();

        try
        {
            // Act
            async Task actAsync() => await handler.InvokeToolAsync(
                serverUrl: "http://localhost:12345/mcp",
                serverLabel: "test",
                toolName: DefaultMcpToolHandler.ListToolsToolName,
                arguments: new Dictionary<string, object?> { ["ignored"] = true },
                headers: null,
                connectionName: null);

            // Assert
            ArgumentException exception = await Assert.ThrowsAsync<ArgumentException>(actAsync);
            Assert.Contains("does not accept tool arguments", exception.Message);
        }
        finally
        {
            await handler.DisposeAsync();
        }
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

    #region Interface Implementation Tests

    [Fact]
    public async Task DefaultMcpToolHandler_ShouldImplementIMcpToolHandlerAsync()
    {
        // Arrange & Act
        DefaultMcpToolHandler handler = new();

        // Assert
        Assert.IsAssignableFrom<IMcpToolHandler>(handler);
        await handler.DisposeAsync();
    }

    [Fact]
    public async Task DefaultMcpToolHandler_ShouldImplementIAsyncDisposableAsync()
    {
        // Arrange & Act
        DefaultMcpToolHandler handler = new();

        // Assert
        Assert.IsAssignableFrom<IAsyncDisposable>(handler);
        await handler.DisposeAsync();
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
