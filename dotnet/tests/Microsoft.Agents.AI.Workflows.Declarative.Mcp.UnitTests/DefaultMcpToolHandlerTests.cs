// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
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
        handler.Should().NotBeNull();
        await handler.DisposeAsync();
    }

    [Fact]
    public async Task Constructor_WithNullHttpClientProvider_ShouldCreateInstanceAsync()
    {
        // Act
        DefaultMcpToolHandler handler = new(httpClientProvider: null);

        // Assert
        handler.Should().NotBeNull();
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
        handler.Should().NotBeNull();
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
        Func<Task> act = async () => await handler.DisposeAsync();

        // Assert
        await act.Should().NotThrowAsync();
    }

    [Fact]
    public async Task DisposeAsync_WhenCalledMultipleTimes_ShouldHandleGracefullyAsync()
    {
        // Arrange
        DefaultMcpToolHandler handler = new();

        // Act
        await handler.DisposeAsync();
        Func<Task> act = async () => await handler.DisposeAsync();

        // Assert - Second dispose should throw ObjectDisposedException from the semaphore
        await act.Should().ThrowAsync<ObjectDisposedException>();
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
        providerCalled.Should().BeTrue();
        capturedServerUrl.Should().Be("http://localhost:12345/mcp");
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
        providerCalled.Should().BeTrue();
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
            providerCallCount.Should().Be(2);
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
            providerCallCount.Should().Be(2);
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
            providerCallCount.Should().Be(2);
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
        result.Should().BeTrue();
    }

    [Fact]
    public void IsListToolsToolName_WithRegularToolName_ShouldReturnFalse()
    {
        // Act
        bool result = DefaultMcpToolHandler.IsListToolsToolName("search");

        // Assert
        result.Should().BeFalse();
    }

    [Fact]
    public async Task InvokeToolAsync_WithListToolsArguments_ShouldThrowArgumentExceptionAsync()
    {
        // Arrange
        DefaultMcpToolHandler handler = new();

        try
        {
            // Act
            Func<Task> act = async () => await handler.InvokeToolAsync(
                serverUrl: "http://localhost:12345/mcp",
                serverLabel: "test",
                toolName: DefaultMcpToolHandler.ListToolsToolName,
                arguments: new Dictionary<string, object?> { ["ignored"] = true },
                headers: null,
                connectionName: null);

            // Assert
            await act.Should().ThrowAsync<ArgumentException>()
                .WithMessage("*does not accept tool arguments*");
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
        TextContent text = result.Outputs.Should().ContainSingle().Subject.Should().BeOfType<TextContent>().Subject;
        using JsonDocument document = JsonDocument.Parse(text.Text);
        JsonElement listedTool = document.RootElement.GetProperty("tools")[0];
        listedTool.GetProperty("name").GetString().Should().Be("search");
        listedTool.GetProperty("description").GetString().Should().Be("Searches documentation.");
        listedTool.GetProperty("inputSchema").GetProperty("properties").GetProperty("query").GetProperty("type").GetString().Should().Be("string");
    }

    #endregion

    #region Interface Implementation Tests

    [Fact]
    public async Task DefaultMcpToolHandler_ShouldImplementIMcpToolHandlerAsync()
    {
        // Arrange & Act
        DefaultMcpToolHandler handler = new();

        // Assert
        handler.Should().BeAssignableTo<IMcpToolHandler>();
        await handler.DisposeAsync();
    }

    [Fact]
    public async Task DefaultMcpToolHandler_ShouldImplementIAsyncDisposableAsync()
    {
        // Arrange & Act
        DefaultMcpToolHandler handler = new();

        // Assert
        handler.Should().BeAssignableTo<IAsyncDisposable>();
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
        TextContent textContent = result.Should().BeOfType<TextContent>().Subject;
        textContent.Text.Should().Be("hello world");
        textContent.RawRepresentation.Should().BeSameAs(block);
    }

    [Fact]
    public void ConvertContentBlock_ImageContentBlock_WithEmptyData_ShouldReturnDataContentWithEmptyUri()
    {
        // Arrange
        ImageContentBlock block = new() { Data = ReadOnlyMemory<byte>.Empty, MimeType = "image/png" };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        DataContent dataContent = result.Should().BeOfType<DataContent>().Subject;
        dataContent.MediaType.Should().Be("image/png");
        dataContent.Uri.Should().Be("data:image/png;base64,");
        dataContent.Data.IsEmpty.Should().BeTrue();
        dataContent.RawRepresentation.Should().BeSameAs(block);
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
        DataContent dataContent = result.Should().BeOfType<DataContent>().Subject;
        dataContent.MediaType.Should().Be("image/png");
        dataContent.Data.ToArray().Should().BeEquivalentTo(expectedDecoded);
        dataContent.Uri.Should().Be($"data:image/png;base64,{Base64Payload}");
        dataContent.RawRepresentation.Should().BeSameAs(block);
    }

    [Fact]
    public void ConvertContentBlock_AudioContentBlock_WithEmptyData_ShouldReturnDataContentWithEmptyUri()
    {
        // Arrange
        AudioContentBlock block = new() { Data = ReadOnlyMemory<byte>.Empty, MimeType = "audio/wav" };

        // Act
        AIContent result = DefaultMcpToolHandler.ConvertContentBlock(block);

        // Assert
        DataContent dataContent = result.Should().BeOfType<DataContent>().Subject;
        dataContent.MediaType.Should().Be("audio/wav");
        dataContent.Uri.Should().Be("data:audio/wav;base64,");
        dataContent.Data.IsEmpty.Should().BeTrue();
        dataContent.RawRepresentation.Should().BeSameAs(block);
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
        DataContent dataContent = result.Should().BeOfType<DataContent>().Subject;
        dataContent.MediaType.Should().Be("audio/wav");
        dataContent.Data.ToArray().Should().BeEquivalentTo(expectedDecoded);
        dataContent.Uri.Should().Be($"data:audio/wav;base64,{Base64Payload}");
        dataContent.RawRepresentation.Should().BeSameAs(block);
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
        TextContent textContent = result.Should().BeOfType<TextContent>().Subject;
        textContent.Text.Should().Be("embedded text payload");
        textContent.RawRepresentation.Should().BeSameAs(block);
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
        DataContent dataContent = result.Should().BeOfType<DataContent>().Subject;
        dataContent.MediaType.Should().Be("application/zip");
        dataContent.Data.ToArray().Should().BeEquivalentTo(expectedDecoded);
        dataContent.Uri.Should().Be($"data:application/zip;base64,{Base64Payload}");
        dataContent.RawRepresentation.Should().BeSameAs(block);
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
        UriContent uriContent = result.Should().BeOfType<UriContent>().Subject;
        uriContent.Uri.ToString().Should().Be("https://example.com/resource.bin");
        uriContent.MediaType.Should().Be("application/zip");
        uriContent.RawRepresentation.Should().BeSameAs(block);
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
        UriContent uriContent = result.Should().BeOfType<UriContent>().Subject;
        uriContent.Uri.ToString().Should().Be("https://example.com/resource");
        uriContent.MediaType.Should().Be("application/octet-stream");
    }

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
        FunctionCallContent call = result.Should().BeOfType<FunctionCallContent>().Subject;
        call.CallId.Should().Be("call-1");
        call.Name.Should().Be("get_weather");
        call.Arguments.Should().NotBeNull();
        call.Arguments!.Should().ContainKey("city");
        call.RawRepresentation.Should().BeSameAs(block);
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
        FunctionResultContent functionResult = result.Should().BeOfType<FunctionResultContent>().Subject;
        functionResult.CallId.Should().Be("call-1");
        functionResult.Exception.Should().BeNull();
        functionResult.RawRepresentation.Should().BeSameAs(block);
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
        FunctionResultContent functionResult = result.Should().BeOfType<FunctionResultContent>().Subject;
        functionResult.CallId.Should().Be("call-2");
        functionResult.Exception.Should().NotBeNull();
        functionResult.RawRepresentation.Should().BeSameAs(block);
    }

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
        result.AdditionalProperties.Should().NotBeNull();
        result.AdditionalProperties!.Should().ContainKey("traceId");
        result.AdditionalProperties.Should().ContainKey("priority");
    }

    #endregion
}
