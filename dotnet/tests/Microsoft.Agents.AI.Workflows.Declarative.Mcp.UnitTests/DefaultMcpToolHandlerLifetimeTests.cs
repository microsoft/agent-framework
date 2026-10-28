// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp.UnitTests;

/// <summary>
/// Functional session-lifetime tests using in-memory and loopback HTTP transports and inert tool results.
/// </summary>
public sealed class DefaultMcpToolHandlerLifetimeTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("2025-11-25")]
    public async Task ParameterlessHandler_SequentialInvocations_DisposeSeparateSessionsBeforeReturningAsync(string? protocolVersion)
    {
        // Arrange
        ProtocolStub stub = new();
        await using LoopbackMcpServer server = new(stub);
        DefaultMcpToolHandler handler = new() { ProtocolVersion = protocolVersion };
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(30));

        // Act
        McpServerToolResultContent first = await handler.InvokeToolAsync(
            server.Endpoint, null, "session", null, null, null, timeout.Token);

        // Assert
        Assert.NotNull(first.Outputs);
        string firstSession = Assert.IsType<TextContent>(Assert.Single(first.Outputs)).Text;
        Assert.Equal(1, stub.Initializations);
        Assert.Equal(1, stub.Terminations);
        Assert.Equal(firstSession, Assert.Single(server.TerminatedSessions));

        // Act
        McpServerToolResultContent second = await handler.InvokeToolAsync(
            server.Endpoint, null, "session", null, null, null, timeout.Token);

        // Assert
        Assert.NotNull(second.Outputs);
        string secondSession = Assert.IsType<TextContent>(Assert.Single(second.Outputs)).Text;
        Assert.NotEqual(firstSession, secondSession);
        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
        Assert.Equal(new[] { firstSession, secondSession }, server.TerminatedSessions);
    }

    [Theory]
    [InlineData(null, 2)]
    [InlineData("2025-11-25", 0)]
    public async Task ProtocolSelection_PreservesPerInvocationInitializationAsync(string? protocolVersion, int expectedDiscoveries)
    {
        // Arrange
        ProtocolStub stub = new();
        DefaultMcpToolHandler handler = CreateHandler(stub, protocolVersion);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        McpServerToolResultContent first = await InvokeAsync(handler, "session", timeout.Token);
        McpServerToolResultContent second = await InvokeAsync(handler, "session", timeout.Token);

        // Assert
        Assert.NotNull(first.Outputs);
        Assert.NotNull(second.Outputs);
        Assert.NotEqual(
            Assert.IsType<TextContent>(Assert.Single(first.Outputs)).Text,
            Assert.IsType<TextContent>(Assert.Single(second.Outputs)).Text);
        Assert.Equal(expectedDiscoveries, stub.DiscoverRequests);
        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ExplicitNewProtocol_DiscoversWithoutLegacyFallbackAsync(bool supportsDiscovery)
    {
        // Arrange
        ProtocolStub stub = new() { SupportsDiscovery = supportsDiscovery };
        DefaultMcpToolHandler handler = CreateHandler(stub, "2026-07-28");
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        if (supportsDiscovery)
        {
            McpServerToolResultContent result = await InvokeAsync(handler, "ping", timeout.Token);
            Assert.NotNull(result.Outputs);
            Assert.Equal("ok", Assert.IsType<TextContent>(Assert.Single(result.Outputs)).Text);
        }
        else
        {
            await Assert.ThrowsAsync<McpException>(() => InvokeAsync(handler, "ping", timeout.Token));
        }

        // Assert
        Assert.Equal(1, stub.DiscoverRequests);
        Assert.Equal(0, stub.Initializations);
        Assert.Equal(0, stub.Terminations);
        Assert.Single(stub.Handlers).Protected().Verify("Dispose", Times.Once(), ItExpr.Is<bool>(disposing => disposing));
    }

    [Fact]
    public async Task ExplicitLegacyProtocol_RejectsVersionMismatchAndDisposesResourcesAsync()
    {
        // Arrange
        ProtocolStub stub = new()
        {
            InitializationProtocolVersion = "2025-06-18",
            OnOperation = _ => Assert.Fail("A tool must not run after a protocol version mismatch.")
        };
        DefaultMcpToolHandler handler = CreateHandler(stub, "2025-11-25");
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        McpException exception = await Assert.ThrowsAsync<McpException>(() => InvokeAsync(handler, "ping", timeout.Token));

        // Assert
        Assert.Contains("protocol version mismatch", exception.Message);
        Assert.Equal(0, stub.DiscoverRequests);
        Assert.Equal(1, stub.Initializations);
        Assert.Equal(1, stub.Terminations);
        Assert.Single(stub.Handlers).Protected().Verify("Dispose", Times.Once(), ItExpr.Is<bool>(disposing => disposing));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RequestOnlyInvocation_DoesNotOpenStandaloneStreamAsync(bool useEventStream)
    {
        // Arrange
        ProtocolStub stub = new() { UseEventStreamResult = useEventStream };
        DefaultMcpToolHandler handler = CreateHandler(stub);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        McpServerToolResultContent result = await InvokeAsync(handler, "ping", timeout.Token);

        // Assert
        Assert.NotNull(result.Outputs);
        Assert.Equal("ok", Assert.IsType<TextContent>(Assert.Single(result.Outputs)).Text);
        Assert.Equal(0, stub.StandaloneGetRequests);
        Assert.Equal(1, stub.Initializations);
        Assert.Equal(1, stub.Terminations);
    }

    [Fact]
    public async Task SequentialInvocations_UseSeparateSessionsAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        DefaultMcpToolHandler handler = CreateHandler(stub);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        McpServerToolResultContent first = await InvokeAsync(handler, "session", timeout.Token);
        McpServerToolResultContent second = await InvokeAsync(handler, "session", timeout.Token);

        // Assert
        Assert.NotNull(first.Outputs);
        Assert.NotNull(second.Outputs);
        Assert.NotEqual(
            Assert.IsType<TextContent>(Assert.Single(first.Outputs)).Text,
            Assert.IsType<TextContent>(Assert.Single(second.Outputs)).Text);
        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
    }

    [Theory]
    [InlineData("ftp://mcp.example/api", false)]
    [InlineData("ftp://mcp.example/api", true)]
    [InlineData("ws://mcp.example/api", false)]
    [InlineData("ws://mcp.example/api", true)]
    public async Task UnsupportedScheme_DoesNotAcquireHttpClientAsync(string serverUrl, bool useFactory)
    {
        // Arrange
        Mock<IHttpClientFactory> factory = new(MockBehavior.Strict);
        DefaultMcpToolHandler handler = useFactory ? new(factory.Object, "workflow-mcp") : new();

        // Act
        await Assert.ThrowsAsync<ArgumentException>(() => handler.InvokeToolAsync(
            serverUrl, null, "ping", null, null, null));

        // Assert
        factory.Verify(f => f.CreateClient(It.IsAny<string>()), Times.Never);
    }

    [Fact]
    public async Task DiscoveryAndToolCalls_DisposeSeparateHttpClientsAndSessionsAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        DefaultMcpToolHandler handler = CreateHandler(stub);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        await InvokeAsync(handler, "ping", timeout.Token);
        await InvokeAsync(handler, DefaultMcpToolHandler.ListToolsToolName, timeout.Token);

        // Assert
        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
        Assert.Equal(2, stub.Handlers.Count);
        foreach (Mock<HttpMessageHandler> transport in stub.Handlers)
        {
            transport.Protected().Verify("Dispose", Times.Once(), ItExpr.Is<bool>(disposing => disposing));
        }
    }

    [Fact]
    public async Task DifferentConnectionNames_DoNotRetainSessionsAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        DefaultMcpToolHandler handler = CreateHandler(stub);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        foreach (string connectionName in new[] { "first", "second", "first" })
        {
            await handler.InvokeToolAsync(
                "https://mcp.example/api", null, "ping", null, null, connectionName, timeout.Token);
        }

        // Assert
        Assert.Equal(3, stub.Initializations);
        Assert.Equal(3, stub.Handlers.Count);
        Assert.Equal(3, stub.Terminations);
    }

    [Fact]
    public async Task DifferentOrigins_KeepRequestConfigurationAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        DefaultMcpToolHandler handler = CreateHandler(stub);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        foreach (string name in new[] { "first", "second" })
        {
            Uri endpoint = new($"https://{name}.example/mcp");
            string headerValue = $"Bearer {name}";
            stub.OnOperation = request =>
            {
                Assert.Equal(endpoint, request.RequestUri);
                Assert.Equal(headerValue, Assert.Single(request.Headers.GetValues("Authorization")));
            };
            await handler.InvokeToolAsync(
                endpoint.AbsoluteUri, name, "ping", null,
                new Dictionary<string, string> { ["Authorization"] = headerValue }, name, timeout.Token);
        }

        // Assert
        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
        Assert.Equal(2, stub.Handlers.Count);
    }

    [Theory]
    [InlineData("session")]
    [InlineData(DefaultMcpToolHandler.ListToolsToolName)]
    public async Task Factory_SequentialInvocations_OwnClientsButReusePooledHandlersAsync(string toolName)
    {
        // Arrange
        const string ClientName = "workflow-mcp";
        ProtocolStub stub = new()
        {
            OnOperation = request => Assert.Equal("configured", Assert.Single(request.Headers.GetValues("X-Client-Configuration")))
        };
        ServiceCollection services = new();
        services.AddHttpClient(ClientName, client => client.DefaultRequestHeaders.Add("X-Client-Configuration", "configured"))
            .ConfigurePrimaryHttpMessageHandler(stub.CreateMessageHandler);
        using ServiceProvider serviceProvider = services.BuildServiceProvider();
        IHttpClientFactory applicationFactory = serviceProvider.GetRequiredService<IHttpClientFactory>();
        List<HttpClient> clients = [];
        Mock<IHttpClientFactory> factory = new();
        Mock<IDisposable> factoryOwner = factory.As<IDisposable>();
        factory.Setup(f => f.CreateClient(ClientName)).Returns(() =>
        {
            HttpClient client = applicationFactory.CreateClient(ClientName);
            clients.Add(client);
            return client;
        });
        DefaultMcpToolHandler handler = new(factory.Object, ClientName);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        McpServerToolResultContent first = await InvokeAsync(handler, toolName, timeout.Token);
        McpServerToolResultContent second = await InvokeAsync(handler, toolName, timeout.Token);

        // Assert
        Assert.Equal(2, clients.Count);
        Assert.NotSame(clients[0], clients[1]);
        if (toolName == "session")
        {
            Assert.NotNull(first.Outputs);
            Assert.NotNull(second.Outputs);
            Assert.NotEqual(
                Assert.IsType<TextContent>(Assert.Single(first.Outputs)).Text,
                Assert.IsType<TextContent>(Assert.Single(second.Outputs)).Text);
        }

        foreach (HttpClient client in clients)
        {
            await Assert.ThrowsAsync<ObjectDisposedException>(() => client.GetAsync(new Uri("https://mcp.example/api"), timeout.Token));
        }

        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
        factory.Verify(f => f.CreateClient(ClientName), Times.Exactly(2));
        factoryOwner.Verify(f => f.Dispose(), Times.Never);
        Assert.Single(stub.Handlers).Protected().Verify("Dispose", Times.Never(), ItExpr.Is<bool>(disposing => disposing));
        using HttpClient subsequentClient = applicationFactory.CreateClient(ClientName);
        using HttpResponseMessage response = await subsequentClient.GetAsync(new Uri("https://mcp.example/api"), timeout.Token);
        Assert.Equal(HttpStatusCode.MethodNotAllowed, response.StatusCode);
    }

    [Theory]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public async Task InvocationFailure_DisposesClientAndAllowsNextInvocationAsync(bool failInitialization, bool failOperation)
    {
        // Arrange
        ProtocolStub stub = new() { FailInitialization = failInitialization, FailOperation = failOperation };
        List<HttpClient> clients = [];
        Mock<IHttpClientFactory> factory = new();
        factory.Setup(f => f.CreateClient("workflow-mcp")).Returns(() =>
        {
            HttpClient client = new(stub.CreateMessageHandler());
            clients.Add(client);
            return client;
        });
        using SemaphoreSlim started = new(0);
        bool cancel = !failInitialization && !failOperation;
        if (cancel)
        {
            stub.BeforeOperationAsync = async token =>
            {
                started.Release();
                await Task.Delay(Timeout.Infinite, token);
            };
        }

        DefaultMcpToolHandler handler = new(factory.Object, "workflow-mcp");
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));
        using CancellationTokenSource cancellation = CancellationTokenSource.CreateLinkedTokenSource(timeout.Token);

        // Act
        Task<McpServerToolResultContent> invocation = InvokeAsync(handler, "ping", cancellation.Token);
        if (cancel)
        {
            await started.WaitAsync(timeout.Token);
            cancellation.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => invocation);
        }
        else
        {
            await Assert.ThrowsAsync<HttpRequestException>(() => invocation);
        }

        HttpClient firstClient = Assert.Single(clients);
        await Assert.ThrowsAsync<ObjectDisposedException>(() => firstClient.GetAsync(new Uri("https://mcp.example/api"), timeout.Token));
        Assert.Single(stub.Handlers).Protected().Verify("Dispose", Times.Once(), ItExpr.Is<bool>(disposing => disposing));
        stub.BeforeOperationAsync = null;
        stub.FailInitialization = false;
        stub.FailOperation = false;
        McpServerToolResultContent result = await InvokeAsync(handler, "ping", timeout.Token);

        // Assert
        Assert.NotNull(result.Outputs);
        Assert.Equal("ok", Assert.IsType<TextContent>(Assert.Single(result.Outputs)).Text);
        Assert.Equal(2, clients.Count);
        Assert.Equal(failInitialization ? 1 : 2, stub.Initializations);
        Assert.Equal(failInitialization ? 1 : 2, stub.Terminations);
        await Assert.ThrowsAsync<ObjectDisposedException>(() => clients[1].GetAsync(new Uri("https://mcp.example/api"), timeout.Token));
        stub.Handlers[1].Protected().Verify("Dispose", Times.Once(), ItExpr.Is<bool>(disposing => disposing));
    }

    [Fact]
    public async Task FactoryFailure_DoesNotPreventNextInvocationAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        Mock<IHttpClientFactory> factory = new();
        factory.SetupSequence(f => f.CreateClient("workflow-mcp"))
            .Throws(new InvalidOperationException("Factory unavailable."))
            .Returns(() => new HttpClient(stub.CreateMessageHandler()));
        DefaultMcpToolHandler handler = new(factory.Object, "workflow-mcp");
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        InvalidOperationException error = await Assert.ThrowsAsync<InvalidOperationException>(
            () => InvokeAsync(handler, "ping", timeout.Token));
        McpServerToolResultContent result = await InvokeAsync(handler, "ping", timeout.Token);

        // Assert
        Assert.Equal("Factory unavailable.", error.Message);
        Assert.NotNull(result.Outputs);
        Assert.Equal("ok", Assert.IsType<TextContent>(Assert.Single(result.Outputs)).Text);
        Assert.Equal(1, stub.Initializations);
        Assert.Equal(1, stub.Terminations);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ConcurrentInvocations_DoNotCoalesceOrSerializeSessionsAsync(bool reuseHandlers)
    {
        // Arrange
        ProtocolStub stub = new();
        using ServiceProvider? serviceProvider = reuseHandlers
            ? new ServiceCollection().AddHttpClient("workflow-mcp")
                .ConfigurePrimaryHttpMessageHandler(stub.CreateMessageHandler).Services.BuildServiceProvider()
            : null;
        using SemaphoreSlim started = new(0);
        using SemaphoreSlim finish = new(0);
        stub.BeforeOperationAsync = async token =>
        {
            started.Release();
            await finish.WaitAsync(token);
        };
        DefaultMcpToolHandler handler = serviceProvider is not null
            ? new(serviceProvider.GetRequiredService<IHttpClientFactory>(), "workflow-mcp")
            : CreateHandler(stub);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        Task<McpServerToolResultContent> first = InvokeAsync(handler, "session", timeout.Token);
        Task<McpServerToolResultContent> second = InvokeAsync(handler, "session", timeout.Token);
        await started.WaitAsync(timeout.Token);
        await started.WaitAsync(timeout.Token);
        finish.Release();
        Task<McpServerToolResultContent> completed = await Task.WhenAny(first, second);
        await completed;
        Assert.False((completed == first ? second : first).IsCompleted);
        Assert.Equal(1, stub.Terminations);
        if (reuseHandlers)
        {
            Assert.Single(stub.Handlers).Protected().Verify("Dispose", Times.Never(), ItExpr.Is<bool>(disposing => disposing));
        }

        finish.Release();
        McpServerToolResultContent[] results = await Task.WhenAll(first, second);

        // Assert
        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
        IList<AIContent>? firstOutputs = results[0].Outputs;
        IList<AIContent>? secondOutputs = results[1].Outputs;
        Assert.NotNull(firstOutputs);
        Assert.NotNull(secondOutputs);
        Assert.NotEqual(
            Assert.IsType<TextContent>(Assert.Single(firstOutputs)).Text,
            Assert.IsType<TextContent>(Assert.Single(secondOutputs)).Text);
        Assert.Equal(reuseHandlers ? 1 : 2, stub.Handlers.Count);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ActiveInvocation_RetainsResourcesUntilCompletionAsync(bool pauseInitialization)
    {
        // Arrange
        ProtocolStub stub = new();
        using SemaphoreSlim started = new(0);
        using SemaphoreSlim finish = new(0);
        async Task PauseAsync(CancellationToken token)
        {
            started.Release();
            await finish.WaitAsync(token);
        }

        if (pauseInitialization)
        {
            stub.BeforeInitializationAsync = PauseAsync;
        }
        else
        {
            stub.BeforeOperationAsync = PauseAsync;
        }

        DefaultMcpToolHandler handler = CreateHandler(stub);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        Task<McpServerToolResultContent> invocation = InvokeAsync(handler, "ping", timeout.Token);
        await started.WaitAsync(timeout.Token);
        Mock<HttpMessageHandler> transport = Assert.Single(stub.Handlers);
        transport.Protected().Verify("Dispose", Times.Never(), ItExpr.Is<bool>(disposing => disposing));
        finish.Release();
        await invocation;

        // Assert
        Assert.Equal(1, stub.Initializations);
        Assert.Equal(1, stub.Terminations);
        transport.Protected().Verify("Dispose", Times.Once(), ItExpr.Is<bool>(disposing => disposing));
    }

    [Theory]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(false, false)]
    public async Task CleanupFailure_DoesNotReplaceOutcomeAsync(bool failInitialization, bool failOperation)
    {
        // Arrange
        ProtocolStub stub = new()
        {
            FailInitialization = failInitialization,
            FailOperation = failOperation,
            FailTransportDisposal = true
        };
        DefaultMcpToolHandler handler = CreateHandler(stub);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));
        using CleanupTraceListener listener = new();
        Trace.Listeners.Add(listener);
        try
        {
            // Act
            if (failInitialization || failOperation)
            {
                await Assert.ThrowsAsync<HttpRequestException>(() => InvokeAsync(handler, "ping", timeout.Token));
            }
            else
            {
                McpServerToolResultContent result = await InvokeAsync(handler, "ping", timeout.Token);
                Assert.NotNull(result.Outputs);
                Assert.Equal("ok", Assert.IsType<TextContent>(Assert.Single(result.Outputs)).Text);
            }

            // Assert
            Assert.Equal(failInitialization ? 0 : 1, stub.Terminations);
            Assert.Contains("Failed to dispose MCP ", listener.Output);
            Assert.Contains("transport cleanup failed", listener.Output);
            Assert.Single(stub.Handlers).Protected().Verify(
                "Dispose", Times.Once(), ItExpr.Is<bool>(disposing => disposing));
        }
        finally
        {
            Trace.Listeners.Remove(listener);
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ClientConnection_SessionCleanupFailure_StillCleansUpTransportAsync(bool cancelSessionCleanup)
    {
        // Arrange
        Mock<McpClient> client = new();
        Exception sessionError = cancelSessionCleanup
            ? new OperationCanceledException("session cleanup cancelled")
            : new InvalidOperationException("session cleanup failed");
        client.Setup(c => c.DisposeAsync()).Returns(new ValueTask(Task.FromException(sessionError)));
        Mock<IAsyncDisposable> transport = new();
        transport.Setup(t => t.DisposeAsync()).Returns(new ValueTask(Task.FromException(
            new InvalidOperationException("transport cleanup failed"))));
        DefaultMcpToolHandler.ClientConnection connection = new(client.Object, transport.Object);
        using CleanupTraceListener listener = new();
        Trace.Listeners.Add(listener);
        try
        {
            // Act
            if (cancelSessionCleanup)
            {
                Assert.Same(sessionError, await Assert.ThrowsAsync<OperationCanceledException>(
                    () => connection.DisposeAsync().AsTask()));
            }
            else
            {
                await connection.DisposeAsync();
                Assert.Contains("Failed to dispose MCP session", listener.Output);
            }

            // Assert
            Assert.Contains("Failed to dispose MCP transport", listener.Output);
            client.Verify(c => c.DisposeAsync(), Times.Once);
            transport.Verify(t => t.DisposeAsync(), Times.Once);
        }
        finally
        {
            Trace.Listeners.Remove(listener);
        }
    }

    private static DefaultMcpToolHandler CreateHandler(ProtocolStub stub, string? protocolVersion = null)
    {
        Mock<IHttpClientFactory> factory = new();
        factory.Setup(f => f.CreateClient("workflow-mcp")).Returns(() => new HttpClient(stub.CreateMessageHandler()));
        return new(factory.Object, "workflow-mcp") { ProtocolVersion = protocolVersion };
    }

    private static Task<McpServerToolResultContent> InvokeAsync(
        DefaultMcpToolHandler handler, string toolName, CancellationToken cancellationToken) =>
        handler.InvokeToolAsync("https://mcp.example/api", null, toolName, null, null, null, cancellationToken);

    private sealed class ProtocolStub
    {
        private int _initializations;
        private int _terminations;
        private int _standaloneGetRequests;
        private int _discoverRequests;

        public int Initializations => this._initializations;
        public int Terminations => this._terminations;
        public int StandaloneGetRequests => this._standaloneGetRequests;
        public int DiscoverRequests => this._discoverRequests;
        public List<Mock<HttpMessageHandler>> Handlers { get; } = [];
        public Func<CancellationToken, Task>? BeforeInitializationAsync { get; set; }
        public Func<CancellationToken, Task>? BeforeOperationAsync { get; set; }
        public Action<HttpRequestMessage>? OnOperation { get; set; }
        public bool FailInitialization { get; set; }
        public bool FailOperation { get; set; }
        public bool FailTransportDisposal { get; set; }
        public bool UseEventStreamResult { get; set; }
        public bool SupportsDiscovery { get; set; }
        public string? InitializationProtocolVersion { get; set; }

        public HttpMessageHandler CreateMessageHandler()
        {
            Mock<HttpMessageHandler> handler = new() { CallBase = true };
            handler.Protected()
                .Setup<Task<HttpResponseMessage>>("SendAsync", ItExpr.IsAny<HttpRequestMessage>(), ItExpr.IsAny<CancellationToken>())
                .Returns<HttpRequestMessage, CancellationToken>(this.SendAsync);
            if (this.FailTransportDisposal)
            {
                handler.Protected().Setup("Dispose", ItExpr.Is<bool>(disposing => disposing))
                    .Throws(new InvalidOperationException("transport cleanup failed"));
            }

            this.Handlers.Add(handler);
            return handler.Object;
        }

        public async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (request.Method == HttpMethod.Get)
            {
                Interlocked.Increment(ref this._standaloneGetRequests);
                return EmptyResponse(HttpStatusCode.MethodNotAllowed, request);
            }

            if (request.Method == HttpMethod.Delete)
            {
                Interlocked.Increment(ref this._terminations);
                return EmptyResponse(HttpStatusCode.OK, request);
            }

            Assert.NotNull(request.Content);
#if NET
            using JsonDocument document = JsonDocument.Parse(await request.Content.ReadAsStringAsync(cancellationToken));
#else
            using JsonDocument document = JsonDocument.Parse(await request.Content.ReadAsStringAsync());
#endif
            JsonElement message = document.RootElement;
            if (!message.TryGetProperty("id", out JsonElement id))
            {
                return EmptyResponse(HttpStatusCode.Accepted, request);
            }

            string? method = message.GetProperty("method").GetString();
            if (method == "server/discover")
            {
                Interlocked.Increment(ref this._discoverRequests);
                const string DiscoverResult = """{"supportedVersions":["2026-07-28"],"capabilities":{"tools":{}}}""";
                string discoverResponse = this.SupportsDiscovery
                    ? $$$"""{"jsonrpc":"2.0","id":{{{id.GetRawText()}}},"result":{{{DiscoverResult}}}}"""
                    : $$$"""{"jsonrpc":"2.0","id":{{{id.GetRawText()}}},"error":{"code":-32601,"message":"Method not found"}}""";
                return new(HttpStatusCode.OK)
                {
                    RequestMessage = request,
                    Content = new StringContent(discoverResponse, Encoding.UTF8, "application/json")
                };
            }

            string result;
            string? sessionId = null;
            if (method == "initialize")
            {
                if (this.BeforeInitializationAsync is not null)
                {
                    await this.BeforeInitializationAsync(cancellationToken);
                }

                if (this.FailInitialization)
                {
                    return EmptyResponse(HttpStatusCode.BadRequest, request);
                }

                sessionId = Interlocked.Increment(ref this._initializations).ToString(CultureInfo.InvariantCulture);
                string protocolVersion = this.InitializationProtocolVersion is null
                    ? message.GetProperty("params").GetProperty("protocolVersion").GetRawText()
                    : JsonSerializer.Serialize(this.InitializationProtocolVersion);
                result = $$$"""{"protocolVersion":{{{protocolVersion}}},"capabilities":{"tools":{}},"serverInfo":{"name":"stub","version":"1.0"}}""";
            }
            else
            {
                this.OnOperation?.Invoke(request);
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
                    "tools/call" when message.GetProperty("params").GetProperty("name").GetString() == "session" =>
                        $$$"""{"content":[{"type":"text","text":"{{{Assert.Single(request.Headers.GetValues("Mcp-Session-Id"))}}}"}]}""",
                    "tools/call" => """{"content":[{"type":"text","text":"ok"}]}""",
                    _ => throw new InvalidOperationException($"Unexpected MCP method: {method}")
                };
            }

            string responseBody = $$$"""{"jsonrpc":"2.0","id":{{{id.GetRawText()}}},"result":{{{result}}}}""";
            bool useEventStream = this.UseEventStreamResult && string.Equals(method, "tools/call", StringComparison.Ordinal);
            HttpResponseMessage response = new(HttpStatusCode.OK)
            {
                RequestMessage = request,
                Content = new StringContent(
                    useEventStream ? $"event: message\ndata: {responseBody}\n\n" : responseBody,
                    Encoding.UTF8, useEventStream ? "text/event-stream" : "application/json")
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

    private sealed class LoopbackMcpServer : IAsyncDisposable
    {
        private readonly TcpListener _listener = new(IPAddress.Loopback, 0);
        private readonly CancellationTokenSource _shutdown = new(TimeSpan.FromSeconds(30));
        private readonly Task _requestsTask;

        public LoopbackMcpServer(ProtocolStub stub)
        {
            this._listener.Start();
            this.Endpoint = $"http://127.0.0.1:{((IPEndPoint)this._listener.LocalEndpoint).Port}/mcp";
            this._requestsTask = this.ProcessRequestsAsync(stub);
        }

        public string Endpoint { get; }

        public List<string> TerminatedSessions { get; } = [];

        public async ValueTask DisposeAsync()
        {
            this._shutdown.Cancel();
            this._listener.Stop();
            try
            {
                await this._requestsTask;
            }
            finally
            {
#if NET
                this._listener.Dispose();
#endif
                this._shutdown.Dispose();
            }
        }

        private async Task ProcessRequestsAsync(ProtocolStub stub)
        {
            CancellationToken cancellationToken = this._shutdown.Token;
            using CancellationTokenRegistration stopListener = cancellationToken.Register(this._listener.Stop);
            try
            {
                while (true)
                {
                    using TcpClient client = await this._listener.AcceptTcpClientAsync();
                    using CancellationTokenRegistration closeClient = cancellationToken.Register(client.Close);
                    using NetworkStream stream = client.GetStream();
                    string requestLine = await ReadLineAsync(stream, cancellationToken);
                    using HttpRequestMessage request = new(new HttpMethod(requestLine.Split(' ')[0]), this.Endpoint);
                    Dictionary<string, string> headers = new(StringComparer.OrdinalIgnoreCase);
                    string header;
                    while ((header = await ReadLineAsync(stream, cancellationToken)).Length > 0)
                    {
                        int separator = header.IndexOf(':');
                        headers.Add(header.Substring(0, separator), header.Substring(separator + 1).Trim());
                    }

                    using MemoryStream body = new();
                    if (headers.TryGetValue("Transfer-Encoding", out string? transferEncoding) &&
                        string.Equals(transferEncoding, "chunked", StringComparison.OrdinalIgnoreCase))
                    {
                        int size;
                        while ((size = int.Parse(await ReadLineAsync(stream, cancellationToken), NumberStyles.HexNumber, CultureInfo.InvariantCulture)) > 0)
                        {
                            byte[] chunk = await ReadBytesAsync(stream, size, cancellationToken);
                            body.Write(chunk, 0, chunk.Length);
                            Assert.Empty(await ReadLineAsync(stream, cancellationToken));
                        }

                        Assert.Empty(await ReadLineAsync(stream, cancellationToken));
                    }
                    else if (headers.TryGetValue("Content-Length", out string? length))
                    {
                        byte[] bytes = await ReadBytesAsync(stream, int.Parse(length, CultureInfo.InvariantCulture), cancellationToken);
                        body.Write(bytes, 0, bytes.Length);
                    }

                    request.Content = new ByteArrayContent(body.ToArray());
                    foreach (KeyValuePair<string, string> pair in headers)
                    {
                        if (!request.Headers.TryAddWithoutValidation(pair.Key, pair.Value))
                        {
                            request.Content.Headers.TryAddWithoutValidation(pair.Key, pair.Value);
                        }
                    }

                    if (request.Method == HttpMethod.Delete)
                    {
                        this.TerminatedSessions.Add(Assert.Single(request.Headers.GetValues("Mcp-Session-Id")));
                    }

                    using HttpResponseMessage response = await stub.SendAsync(request, cancellationToken);
                    byte[] content = await response.Content.ReadAsByteArrayAsync();
                    StringBuilder responseHeaders = new($"HTTP/1.1 {(int)response.StatusCode} {response.ReasonPhrase}\r\n");
                    foreach (KeyValuePair<string, IEnumerable<string>> pair in response.Headers)
                    {
                        responseHeaders.Append($"{pair.Key}: {string.Join(", ", pair.Value)}\r\n");
                    }

                    responseHeaders.Append($"Content-Type: {response.Content.Headers.ContentType}\r\nContent-Length: {content.Length}\r\nConnection: close\r\n\r\n");
                    byte[] headerBytes = Encoding.ASCII.GetBytes(responseHeaders.ToString());
#if NET
                    await stream.WriteAsync(headerBytes, cancellationToken);
                    await stream.WriteAsync(content, cancellationToken);
#else
                    await stream.WriteAsync(headerBytes, 0, headerBytes.Length, cancellationToken);
                    await stream.WriteAsync(content, 0, content.Length, cancellationToken);
#endif
                }
            }
            catch (Exception exception) when (cancellationToken.IsCancellationRequested &&
                exception is SocketException or ObjectDisposedException or IOException or OperationCanceledException)
            {
                Trace.WriteLine($"Loopback MCP server stopped: {exception.Message}");
            }
        }

        private static async Task<string> ReadLineAsync(NetworkStream stream, CancellationToken cancellationToken)
        {
            StringBuilder line = new();
            byte[] buffer = new byte[1];
#if NET
            while (await stream.ReadAsync(buffer, cancellationToken) > 0)
#else
            while (await stream.ReadAsync(buffer, 0, 1, cancellationToken) > 0)
#endif
            {
                if (buffer[0] == '\n')
                {
                    return line.ToString().TrimEnd('\r');
                }

                line.Append((char)buffer[0]);
            }

            throw new EndOfStreamException("The HTTP request ended before its headers were complete.");
        }

        private static async Task<byte[]> ReadBytesAsync(NetworkStream stream, int count, CancellationToken cancellationToken)
        {
            byte[] buffer = new byte[count];
            int offset = 0;
            while (offset < count)
            {
#if NET
                int read = await stream.ReadAsync(buffer.AsMemory(offset, count - offset), cancellationToken);
#else
                int read = await stream.ReadAsync(buffer, offset, count - offset, cancellationToken);
#endif
                if (read == 0)
                {
                    throw new EndOfStreamException("The HTTP request ended before its body was complete.");
                }

                offset += read;
            }

            return buffer;
        }
    }

    private sealed class CleanupTraceListener : TraceListener
    {
        private readonly StringBuilder _output = new();

        public string Output => this._output.ToString();

        public override void Write(string? message) => this._output.Append(message);

        public override void WriteLine(string? message) => this._output.AppendLine(message);
    }
}
