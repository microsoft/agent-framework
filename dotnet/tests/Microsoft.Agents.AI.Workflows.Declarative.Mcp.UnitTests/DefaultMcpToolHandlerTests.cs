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
        DefaultMcpToolHandler handler = new(httpClientProvider: null);

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

        // Assert - Second dispose should throw ObjectDisposedException from the semaphore
        await Assert.ThrowsAsync<ObjectDisposedException>(actAsync);
    }

    #endregion

    #region HttpClientProvider Tests

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

    #region Caching Tests

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
            // Since there's no real server, the McpClient.CreateAsync will fail,
            // so the client won't be cached and the provider will be called each time
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

            // Assert - Provider is called each time because McpClient creation fails before caching
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

            // Assert - Different headers should create different cache keys
            Assert.Equal(2, providerCallCount);
        }
        finally
        {
            await handler.DisposeAsync();
        }
    }

    #endregion

    #region ComputeHeadersHash Tests

    [Fact]
    public void ComputeHeadersHash_WithNullHeaders_ReturnsEmptyString()
    {
        // Act
        string result = DefaultMcpToolHandler.ComputeHeadersHash(null);

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void ComputeHeadersHash_WithEmptyHeaders_ReturnsEmptyString()
    {
        // Act
        string result = DefaultMcpToolHandler.ComputeHeadersHash(new Dictionary<string, string>());

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void ComputeHeadersHash_SameHeadersDifferentOrder_ReturnsSameHash()
    {
        // Arrange
        Dictionary<string, string> headers1 = new()
        {
            ["Authorization"] = "Bearer token123",
            ["X-Custom"] = "value1"
        };
        Dictionary<string, string> headers2 = new()
        {
            ["X-Custom"] = "value1",
            ["Authorization"] = "Bearer token123"
        };

        // Act
        string hash1 = DefaultMcpToolHandler.ComputeHeadersHash(headers1);
        string hash2 = DefaultMcpToolHandler.ComputeHeadersHash(headers2);

        // Assert
        Assert.Equal(hash2, hash1);
    }

    [Fact]
    public void ComputeHeadersHash_SameKeysDifferentCaseKeys_ReturnsSameHash()
    {
        // Arrange — RFC 7230: header names are case-insensitive
        Dictionary<string, string> headers1 = new() { ["Authorization"] = "Bearer token" };
        Dictionary<string, string> headers2 = new() { ["authorization"] = "Bearer token" };

        // Act
        string hash1 = DefaultMcpToolHandler.ComputeHeadersHash(headers1);
        string hash2 = DefaultMcpToolHandler.ComputeHeadersHash(headers2);

        // Assert
        Assert.Equal(hash2, hash1);
    }

    [Fact]
    public void ComputeHeadersHash_SameKeysDifferentCaseValues_ReturnsDifferentHash()
    {
        // Arrange — RFC 7235: credentials are case-sensitive
        Dictionary<string, string> headers1 = new() { ["Authorization"] = "Bearer ABC" };
        Dictionary<string, string> headers2 = new() { ["Authorization"] = "Bearer abc" };

        // Act
        string hash1 = DefaultMcpToolHandler.ComputeHeadersHash(headers1);
        string hash2 = DefaultMcpToolHandler.ComputeHeadersHash(headers2);

        // Assert
        Assert.NotEqual(hash2, hash1);
    }

    [Fact]
    public void ComputeHeadersHash_DifferentHeaders_ReturnsDifferentHash()
    {
        // Arrange
        Dictionary<string, string> headers1 = new() { ["Authorization"] = "Bearer token1" };
        Dictionary<string, string> headers2 = new() { ["Authorization"] = "Bearer token2" };

        // Act
        string hash1 = DefaultMcpToolHandler.ComputeHeadersHash(headers1);
        string hash2 = DefaultMcpToolHandler.ComputeHeadersHash(headers2);

        // Assert
        Assert.NotEqual(hash2, hash1);
    }

    #endregion

    #region Cache Key Discrimination Tests

    // These tests exercise BuildCacheKey directly because the integration path
    // (InvokeToolAsync against a fake server) doesn't surface cache-hit behavior
    // without standing up a real MCP server — McpClient.CreateAsync fails before
    // _clients[key] = newClient runs, so nothing ever gets cached.
    // Tuple equality on the returned 4-tuple verifies that the dimensions
    // collectively discriminate cache entries.

    [Fact]
    public void BuildCacheKey_SameInputs_ReturnsEqualKeys()
    {
        // Arrange
        Dictionary<string, string> headers = new() { ["Authorization"] = "Bearer token" };

        // Act
        var key1 = DefaultMcpToolHandler.BuildCacheKey("http://localhost/mcp", "label", "conn", headers);
        var key2 = DefaultMcpToolHandler.BuildCacheKey("http://localhost/mcp", "label", "conn", headers);

        // Assert
        Assert.Equal(key2, key1);
    }

    [Fact]
    public void BuildCacheKey_DifferentConnectionName_ReturnsDifferentKeys()
    {
        // Act
        var key1 = DefaultMcpToolHandler.BuildCacheKey("http://localhost/mcp", "label", "connection-a", null);
        var key2 = DefaultMcpToolHandler.BuildCacheKey("http://localhost/mcp", "label", "connection-b", null);

        // Assert
        Assert.NotEqual(key2, key1);
        Assert.Equal("connection-a", key1.Connection);
        Assert.Equal("connection-b", key2.Connection);
    }

    [Fact]
    public void BuildCacheKey_DifferentServerLabel_ReturnsDifferentKeys()
    {
        // Act
        var key1 = DefaultMcpToolHandler.BuildCacheKey("http://localhost/mcp", "label-a", null, null);
        var key2 = DefaultMcpToolHandler.BuildCacheKey("http://localhost/mcp", "label-b", null, null);

        // Assert
        Assert.NotEqual(key2, key1);
        Assert.Equal("label-a", key1.Label);
        Assert.Equal("label-b", key2.Label);
    }

    [Fact]
    public void BuildCacheKey_CaseSensitiveUrlPath_ReturnsDifferentKeys()
    {
        // Arrange — RFC 3986: URL path is case-sensitive
        // Act
        var key1 = DefaultMcpToolHandler.BuildCacheKey("http://localhost/Tools", null, null, null);
        var key2 = DefaultMcpToolHandler.BuildCacheKey("http://localhost/tools", null, null, null);

        // Assert
        Assert.NotEqual(key2, key1);
    }

    [Fact]
    public void BuildCacheKey_HeaderValuesCaseSensitive_ReturnsDifferentKeys()
    {
        // Arrange — RFC 7235: credentials are case-sensitive
        Dictionary<string, string> headers1 = new() { ["Authorization"] = "Bearer ABC" };
        Dictionary<string, string> headers2 = new() { ["Authorization"] = "Bearer abc" };

        // Act
        var key1 = DefaultMcpToolHandler.BuildCacheKey("http://localhost/mcp", null, null, headers1);
        var key2 = DefaultMcpToolHandler.BuildCacheKey("http://localhost/mcp", null, null, headers2);

        // Assert — header value case must propagate into the cache key
        Assert.NotEqual(key2, key1);
        Assert.NotEqual(key2.HeadersHash, key1.HeadersHash);
    }

    [Fact]
    public void BuildCacheKey_NullLabelAndConnection_NormalizesToEmptyString()
    {
        // Act
        var key = DefaultMcpToolHandler.BuildCacheKey("http://localhost/mcp", null, null, null);

        // Assert — verifies null-safety contract callers rely on
        Assert.Equal(string.Empty, key.Label);
        Assert.Equal(string.Empty, key.Connection);
        Assert.Equal(string.Empty, key.HeadersHash);
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

    #region Origin Pinning Tests

    [Fact]
    public void StripCredentialHeadersOnCrossOrigin_SameOrigin_RetainsAuthorization()
    {
        // Arrange
        using HttpRequestMessage request = new(HttpMethod.Post, "https://trusted.example.com/mcp/message");
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer secret-token");

        // Act
        OriginPinningHandler.StripCredentialHeadersOnCrossOrigin(request, new Uri("https://trusted.example.com"));

        // Assert — same origin, credential is preserved
        Assert.True(request.Headers.Contains("Authorization"));
    }

    [Fact]
    public void StripCredentialHeadersOnCrossOrigin_DifferentHost_RemovesAuthorization()
    {
        // Arrange — server-advertised endpoint on an attacker origin
        using HttpRequestMessage request = new(HttpMethod.Post, "https://attacker.example/collect");
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer secret-token");

        // Act
        OriginPinningHandler.StripCredentialHeadersOnCrossOrigin(request, new Uri("https://trusted.example.com"));

        // Assert — credential must not cross the origin boundary
        Assert.False(request.Headers.Contains("Authorization"));
    }

    [Fact]
    public void StripCredentialHeadersOnCrossOrigin_DifferentPort_RemovesAuthorization()
    {
        // Arrange — same host but a different port is a different origin
        using HttpRequestMessage request = new(HttpMethod.Post, "https://trusted.example.com:8443/mcp");
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer secret-token");

        // Act
        OriginPinningHandler.StripCredentialHeadersOnCrossOrigin(request, new Uri("https://trusted.example.com"));

        // Assert
        Assert.False(request.Headers.Contains("Authorization"));
    }

    [Fact]
    public void StripCredentialHeadersOnCrossOrigin_ExplicitDefaultPort_RetainsAuthorization()
    {
        // Arrange — pinned endpoint carries an explicit :443 while the request omits it; these are
        // the same origin and Uri.Compare must normalize the default port rather than strip.
        using HttpRequestMessage request = new(HttpMethod.Post, "https://trusted.example.com/mcp/message");
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer secret-token");

        // Act
        OriginPinningHandler.StripCredentialHeadersOnCrossOrigin(request, new Uri("https://trusted.example.com:443/mcp"));

        // Assert — explicit vs implicit default port is the same origin
        Assert.True(request.Headers.Contains("Authorization"));
    }

    [Fact]
    public void StripCredentialHeadersOnCrossOrigin_RelativeRequestUri_RetainsAuthorization()
    {
        // Arrange — a relative URI resolves against the client's base address (the pinned origin) and
        // therefore can never target a foreign origin. It must not throw and must retain credentials.
        using HttpRequestMessage request = new(HttpMethod.Post, new Uri("/mcp/message", UriKind.Relative));
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer secret-token");

        // Act
        void act() => OriginPinningHandler.StripCredentialHeadersOnCrossOrigin(request, new Uri("https://trusted.example.com"));

        // Assert — does not throw and leaves the credential in place
        Assert.Null(Record.Exception(act));
        Assert.True(request.Headers.Contains("Authorization"));
    }

    [Fact]
    public void StripCredentialHeadersOnCrossOrigin_DifferentScheme_RemovesAuthorization()
    {
        // Arrange — downgrade to http is a different origin (and would leak over plaintext)
        using HttpRequestMessage request = new(HttpMethod.Post, "http://trusted.example.com/mcp");
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer secret-token");

        // Act
        OriginPinningHandler.StripCredentialHeadersOnCrossOrigin(request, new Uri("https://trusted.example.com"));

        // Assert
        Assert.False(request.Headers.Contains("Authorization"));
    }

    [Fact]
    public void StripCredentialHeadersOnCrossOrigin_CrossOrigin_RemovesCookieAndProxyAuthorization()
    {
        // Arrange
        using HttpRequestMessage request = new(HttpMethod.Post, "https://attacker.example/collect");
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer secret-token");
        request.Headers.TryAddWithoutValidation("Cookie", "session=abc");
        request.Headers.TryAddWithoutValidation("Proxy-Authorization", "Bearer proxy-token");

        // Act
        OriginPinningHandler.StripCredentialHeadersOnCrossOrigin(request, new Uri("https://trusted.example.com"));

        // Assert — all credential-bearing headers are stripped
        Assert.False(request.Headers.Contains("Authorization"));
        Assert.False(request.Headers.Contains("Cookie"));
        Assert.False(request.Headers.Contains("Proxy-Authorization"));
    }

    [Fact]
    public void StripCredentialHeadersOnCrossOrigin_CrossOrigin_PreservesNonCredentialHeaders()
    {
        // Arrange
        using HttpRequestMessage request = new(HttpMethod.Post, "https://attacker.example/collect");
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer secret-token");
        request.Headers.TryAddWithoutValidation("X-Trace-Id", "trace-123");

        // Act
        OriginPinningHandler.StripCredentialHeadersOnCrossOrigin(request, new Uri("https://trusted.example.com"));

        // Assert — only credential headers are removed; other headers are untouched
        Assert.False(request.Headers.Contains("Authorization"));
        Assert.True(request.Headers.Contains("X-Trace-Id"));
    }

    [Fact]
    public async Task OriginPinningHandler_CrossOriginRequest_DoesNotForwardAuthorizationAsync()
    {
        // Arrange — capture what the inner handler actually receives on the wire
        CapturingHandler inner = new();
        using OriginPinningHandler pinning = new(new Uri("https://trusted.example.com/mcp")) { InnerHandler = inner };
        using HttpMessageInvoker invoker = new(pinning);

        using HttpRequestMessage request = new(HttpMethod.Post, "https://attacker.example/collect");
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer secret-token");

        // Act
        using HttpResponseMessage response = await invoker.SendAsync(request, CancellationToken.None);

        // Assert — the credential never reached the inner handler for the foreign origin
        Assert.Equal(System.Net.HttpStatusCode.OK, response.StatusCode);
        Assert.False(inner.LastRequestHadAuthorization);
    }

    [Fact]
    public async Task OriginPinningHandler_SameOriginRequest_ForwardsAuthorizationAsync()
    {
        // Arrange
        CapturingHandler inner = new();
        using OriginPinningHandler pinning = new(new Uri("https://trusted.example.com/mcp")) { InnerHandler = inner };
        using HttpMessageInvoker invoker = new(pinning);

        using HttpRequestMessage request = new(HttpMethod.Post, "https://trusted.example.com/mcp/message");
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer secret-token");

        // Act
        using HttpResponseMessage response = await invoker.SendAsync(request, CancellationToken.None);

        // Assert — same-origin credential flows through normally
        Assert.Equal(System.Net.HttpStatusCode.OK, response.StatusCode);
        Assert.True(inner.LastRequestHadAuthorization);
    }

    private sealed class CapturingHandler : HttpMessageHandler
    {
        public bool LastRequestHadAuthorization { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this.LastRequestHadAuthorization = request.Headers.Contains("Authorization");
            return Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK));
        }
    }

    #endregion
}
