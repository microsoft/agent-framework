// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;

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
}
