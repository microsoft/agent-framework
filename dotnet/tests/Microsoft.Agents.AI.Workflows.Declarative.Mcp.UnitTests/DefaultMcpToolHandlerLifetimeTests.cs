// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp.UnitTests;

/// <summary>
/// Functional session-lifetime tests using an in-memory HTTP transport and inert tool results.
/// </summary>
[System.Diagnostics.CodeAnalysis.SuppressMessage("Reliability", "CA2025:Do not pass disposable objects into unawaited tasks",
    Justification = "Provider callbacks return completed tasks; each invocation and handler disposal is awaited before disposing caller-owned clients.")]
public sealed class DefaultMcpToolHandlerLifetimeTests
{
    [Theory]
    [InlineData("ping")]
    [InlineData(DefaultMcpToolHandler.ListToolsToolName)]
    public async Task Provider_SequentialInvocations_CreateAndDisposeSeparateSessionsAsync(string toolName)
    {
        // Arrange
        ProtocolStub stub = new();
        using HttpClient client = new(stub.CreateMessageHandler());
        int providerCalls = 0;
        DefaultMcpToolHandler handler = new((_, _) =>
        {
            providerCalls++;
            return Task.FromResult<HttpClient?>(client);
        });
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        await InvokeAsync(handler, toolName, timeout.Token);
        Assert.Equal(1, stub.Terminations);
        await InvokeAsync(handler, toolName, timeout.Token);
        await handler.DisposeAsync();

        // Assert
        Assert.Equal(2, providerCalls);
        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
        stub.Handlers[0].Protected().Verify("Dispose", Times.Never(), ItExpr.Is<bool>(disposing => disposing));
    }

    [Fact]
    public async Task ProviderReturningNull_DisposesFallbackTransportPerInvocationAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        int providerCalls = 0;
        await using DefaultMcpToolHandler handler = new((_, _) =>
        {
            providerCalls++;
            return Task.FromResult<HttpClient?>(null);
        }, stub.CreateMessageHandler);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        await InvokeAsync(handler, "ping", timeout.Token);
        await InvokeAsync(handler, "ping", timeout.Token);

        // Assert
        Assert.Equal(2, providerCalls);
        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
        Assert.Equal(2, stub.Handlers.Count);
        foreach (Mock<HttpMessageHandler> transport in stub.Handlers)
        {
            transport.Protected().Verify("Dispose", Times.AtLeastOnce(), ItExpr.Is<bool>(disposing => disposing));
        }
    }

    [Fact]
    public async Task NoProvider_ReusesSessionUntilHandlerDisposalAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        DefaultMcpToolHandler handler = new(null, stub.CreateMessageHandler);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        await InvokeAsync(handler, "ping", timeout.Token);
        await InvokeAsync(handler, DefaultMcpToolHandler.ListToolsToolName, timeout.Token);

        // Assert
        Assert.Equal(1, stub.Initializations);
        Assert.Equal(0, stub.Terminations);
        Mock<HttpMessageHandler> transport = Assert.Single(stub.Handlers);
        transport.Protected().Verify("Dispose", Times.Never(), ItExpr.Is<bool>(disposing => disposing));

        await handler.DisposeAsync();
        Assert.Equal(1, stub.Terminations);
        transport.Protected().Verify("Dispose", Times.AtLeastOnce(), ItExpr.Is<bool>(disposing => disposing));
    }

    [Fact]
    public async Task NoProvider_DifferentConnectionNames_UseSeparateCachedSessionsAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        DefaultMcpToolHandler handler = new(null, stub.CreateMessageHandler);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        foreach (string connectionName in new[] { "first", "second", "first" })
        {
            await handler.InvokeToolAsync(
                "https://mcp.example/api", null, "ping", null, null, connectionName, timeout.Token);
        }

        // Assert
        Assert.Equal(2, stub.Initializations);
        Assert.Single(stub.Handlers);
        Assert.Equal(0, stub.Terminations);
        await handler.DisposeAsync();
        Assert.Equal(2, stub.Terminations);
    }

    [Fact]
    public async Task Provider_Failure_DoesNotPreventHandlerDisposalAsync()
    {
        // Arrange
        int providerCalls = 0;
        DefaultMcpToolHandler handler = new((_, _) =>
        {
            providerCalls++;
            throw new InvalidOperationException("Provider unavailable.");
        });
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => InvokeAsync(handler, "ping", timeout.Token));
        await handler.DisposeAsync();
        await Assert.ThrowsAsync<ObjectDisposedException>(() => InvokeAsync(handler, "ping", timeout.Token));

        // Assert
        Assert.Equal("Provider unavailable.", exception.Message);
        Assert.Equal(1, providerCalls);
    }

    [Fact]
    public async Task Provider_ConcurrentInvocations_DoNotCoalesceOrSerializeSessionsAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        using HttpClient client = new(stub.CreateMessageHandler());
        using SemaphoreSlim started = new(0);
        using SemaphoreSlim finish = new(0);
        stub.BeforeOperationAsync = async token =>
        {
            started.Release();
            await finish.WaitAsync(token);
        };
        int providerCalls = 0;
        await using DefaultMcpToolHandler handler = new((_, _) =>
        {
            Interlocked.Increment(ref providerCalls);
            return Task.FromResult<HttpClient?>(client);
        });
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        Task<McpServerToolResultContent> first = InvokeAsync(handler, "ping", timeout.Token);
        Task<McpServerToolResultContent> second = InvokeAsync(handler, "ping", timeout.Token);
        await started.WaitAsync(timeout.Token);
        await started.WaitAsync(timeout.Token);
        finish.Release(2);
        await Task.WhenAll(first, second);

        // Assert
        Assert.Equal(2, providerCalls);
        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
    }

    [Fact]
    public async Task Provider_OperationFailure_DisposesSessionAndPreservesCallerClientAsync()
    {
        // Arrange
        ProtocolStub stub = new() { FailOperation = true };
        using HttpClient client = new(stub.CreateMessageHandler());
        await using DefaultMcpToolHandler handler = new((_, _) => Task.FromResult<HttpClient?>(client));
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        await Assert.ThrowsAsync<HttpRequestException>(() => InvokeAsync(handler, "ping", timeout.Token));

        // Assert
        Assert.Equal(1, stub.Initializations);
        Assert.Equal(1, stub.Terminations);
        stub.Handlers[0].Protected().Verify("Dispose", Times.Never(), ItExpr.Is<bool>(disposing => disposing));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Provider_InitializationFailure_RespectsTransportOwnershipAsync(bool provideClient)
    {
        // Arrange
        ProtocolStub stub = new() { FailInitialization = true };
        using HttpClient? client = provideClient ? new(stub.CreateMessageHandler()) : null;
        await using DefaultMcpToolHandler handler = new(
            (_, _) => Task.FromResult(client), stub.CreateMessageHandler);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        await Assert.ThrowsAsync<HttpRequestException>(() => InvokeAsync(handler, "ping", timeout.Token));

        // Assert
        Mock<HttpMessageHandler> transport = Assert.Single(stub.Handlers);
        transport.Protected().Verify("Dispose", provideClient ? Times.Never() : Times.AtLeastOnce(), ItExpr.Is<bool>(disposing => disposing));
    }

    [Fact]
    public async Task Provider_Cancellation_DisposesSessionAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        using HttpClient client = new(stub.CreateMessageHandler());
        using SemaphoreSlim started = new(0);
        stub.BeforeOperationAsync = async token =>
        {
            started.Release();
            await Task.Delay(Timeout.Infinite, token);
        };
        await using DefaultMcpToolHandler handler = new((_, _) => Task.FromResult<HttpClient?>(client));
        using CancellationTokenSource cancellation = new(TimeSpan.FromSeconds(10));

        // Act
        Task<McpServerToolResultContent> invocation = InvokeAsync(handler, "ping", cancellation.Token);
        await started.WaitAsync(cancellation.Token);
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => invocation);

        // Assert
        Assert.Equal(1, stub.Terminations);
        stub.Handlers[0].Protected().Verify("Dispose", Times.Never(), ItExpr.Is<bool>(disposing => disposing));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DisposeAsync_WaitsForProviderInvocationCleanupAsync(bool pauseProvider)
    {
        // Arrange
        ProtocolStub stub = new();
        using HttpClient client = new(stub.CreateMessageHandler());
        using SemaphoreSlim started = new(0);
        using SemaphoreSlim finish = new(0);
        async Task PauseAsync(CancellationToken token)
        {
            started.Release();
            await finish.WaitAsync(token);
        }

        if (!pauseProvider)
        {
            stub.BeforeOperationAsync = PauseAsync;
        }

        int providerCalls = 0;
        DefaultMcpToolHandler handler = new(async (_, token) =>
        {
            providerCalls++;
            if (pauseProvider)
            {
                await PauseAsync(token);
            }

            return client;
        });
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        Task<McpServerToolResultContent> invocation = InvokeAsync(handler, "ping", timeout.Token);
        await started.WaitAsync(timeout.Token);
        Task disposal = handler.DisposeAsync().AsTask();
        Assert.False(disposal.IsCompleted);
        await Assert.ThrowsAsync<ObjectDisposedException>(() => InvokeAsync(handler, "ping", timeout.Token));
        finish.Release();
        await invocation;
        await disposal;

        // Assert
        Assert.Equal(1, providerCalls);
        Assert.Equal(1, stub.Terminations);
        stub.Handlers[0].Protected().Verify("Dispose", Times.Never(), ItExpr.Is<bool>(disposing => disposing));
    }

    [Fact]
    public async Task Provider_InvalidDiscoveryArguments_DoesNotCallProviderAsync()
    {
        // Arrange
        int providerCalls = 0;
        await using DefaultMcpToolHandler handler = new((_, _) =>
        {
            providerCalls++;
            return Task.FromResult<HttpClient?>(null);
        });

        // Act
        await Assert.ThrowsAsync<ArgumentException>(() => handler.InvokeToolAsync(
            "https://mcp.example/api", null, DefaultMcpToolHandler.ListToolsToolName,
            new Dictionary<string, object?> { ["unused"] = true }, null, null));

        // Assert
        Assert.Equal(0, providerCalls);
    }

    private static Task<McpServerToolResultContent> InvokeAsync(
        DefaultMcpToolHandler handler, string toolName, CancellationToken cancellationToken) =>
        handler.InvokeToolAsync("https://mcp.example/api", null, toolName, null, null, null, cancellationToken);

    private sealed class ProtocolStub
    {
        private int _initializations;
        private int _terminations;

        public int Initializations => this._initializations;
        public int Terminations => this._terminations;
        public List<Mock<HttpMessageHandler>> Handlers { get; } = [];
        public Func<CancellationToken, Task>? BeforeOperationAsync { get; set; }
        public bool FailInitialization { get; set; }
        public bool FailOperation { get; set; }

        public HttpMessageHandler CreateMessageHandler()
        {
            Mock<HttpMessageHandler> handler = new() { CallBase = true };
            handler.Protected()
                .Setup<Task<HttpResponseMessage>>("SendAsync", ItExpr.IsAny<HttpRequestMessage>(), ItExpr.IsAny<CancellationToken>())
                .Returns<HttpRequestMessage, CancellationToken>(this.SendAsync);
            this.Handlers.Add(handler);
            return handler.Object;
        }

        private async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (request.Method == HttpMethod.Get)
            {
                return EmptyResponse(HttpStatusCode.MethodNotAllowed, request);
            }

            if (request.Method == HttpMethod.Delete)
            {
                Interlocked.Increment(ref this._terminations);
                return EmptyResponse(HttpStatusCode.OK, request);
            }

#if NET
            using JsonDocument document = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(cancellationToken));
#else
            using JsonDocument document = JsonDocument.Parse(await request.Content!.ReadAsStringAsync());
#endif
            JsonElement message = document.RootElement;
            if (!message.TryGetProperty("id", out JsonElement id))
            {
                return EmptyResponse(HttpStatusCode.Accepted, request);
            }

            string? method = message.GetProperty("method").GetString();
            if (method == "server/discover")
            {
                return new(HttpStatusCode.OK)
                {
                    RequestMessage = request,
                    Content = new StringContent(
                        $$$"""{"jsonrpc":"2.0","id":{{{id.GetRawText()}}},"error":{"code":-32601,"message":"Method not found"}}""",
                        Encoding.UTF8, "application/json")
                };
            }

            string result;
            string? sessionId = null;
            if (method == "initialize")
            {
                if (this.FailInitialization)
                {
                    return EmptyResponse(HttpStatusCode.BadRequest, request);
                }

                sessionId = Interlocked.Increment(ref this._initializations).ToString(CultureInfo.InvariantCulture);
                string protocolVersion = message.GetProperty("params").GetProperty("protocolVersion").GetRawText();
                result = $$$"""{"protocolVersion":{{{protocolVersion}}},"capabilities":{"tools":{}},"serverInfo":{"name":"stub","version":"1.0"}}""";
            }
            else
            {
                if (this.BeforeOperationAsync is not null)
                {
                    await this.BeforeOperationAsync(cancellationToken);
                }

                if (this.FailOperation)
                {
                    return EmptyResponse(HttpStatusCode.BadRequest, request);
                }

                result = method switch
                {
                    "tools/list" => """{"tools":[]}""",
                    "tools/call" => """{"content":[{"type":"text","text":"ok"}]}""",
                    _ => throw new InvalidOperationException($"Unexpected MCP method: {method}")
                };
            }

            HttpResponseMessage response = new(HttpStatusCode.OK)
            {
                RequestMessage = request,
                Content = new StringContent(
                    $$$"""{"jsonrpc":"2.0","id":{{{id.GetRawText()}}},"result":{{{result}}}}""",
                    Encoding.UTF8, "application/json")
            };
            if (sessionId is not null)
            {
                response.Headers.Add("Mcp-Session-Id", sessionId);
            }

            return response;
        }

        private static HttpResponseMessage EmptyResponse(HttpStatusCode statusCode, HttpRequestMessage request) =>
            new(statusCode)
            {
                RequestMessage = request,
                Content = new ByteArrayContent([])
            };
    }
}
