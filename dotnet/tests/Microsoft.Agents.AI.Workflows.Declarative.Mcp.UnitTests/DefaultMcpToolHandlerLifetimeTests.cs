// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using ModelContextProtocol.Client;
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
    [Fact]
    public async Task NoProvider_SequentialInvocations_UseSeparateSessionsAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        await using DefaultMcpToolHandler handler = new(null, stub.CreateMessageHandler);
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
    [InlineData("ftp://mcp.example/api", false, false)]
    [InlineData("ftp://mcp.example/api", true, false)]
    [InlineData("ftp://mcp.example/api", false, true)]
    [InlineData("ws://mcp.example/api", false, false)]
    [InlineData("ws://mcp.example/api", true, false)]
    [InlineData("ws://mcp.example/api", false, true)]
    public async Task UnsupportedScheme_DoesNotAcquireHttpClientAsync(string serverUrl, bool useProvider, bool useFactory)
    {
        // Arrange
        using HttpClient client = new();
        using HttpMessageHandler messageHandler = Mock.Of<HttpMessageHandler>();
        bool clientAcquired = false;
        HttpClient AcquireClient()
        {
            clientAcquired = true;
            return client;
        }

        HttpMessageHandler CreateMessageHandler()
        {
            clientAcquired = true;
            return messageHandler;
        }

        Mock<IHttpClientFactory> factory = new();
        factory.Setup(f => f.CreateClient("workflow-mcp")).Returns(AcquireClient);
        await using DefaultMcpToolHandler handler = useFactory
            ? new(factory.Object, "workflow-mcp")
            : new(useProvider ? (_, _) => Task.FromResult<HttpClient?>(AcquireClient()) : null, CreateMessageHandler);

        // Act
        await Assert.ThrowsAsync<ArgumentException>(() => handler.InvokeToolAsync(
            serverUrl, null, "ping", null, null, null));

        // Assert
        Assert.False(clientAcquired);
    }

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
    public async Task ProviderReturningNull_DisposesSeparateHttpClientsAndSessionsAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        int providerCalls = 0;
        DefaultMcpToolHandler handler = new((_, _) =>
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
            transport.Protected().Verify("Dispose", Times.Once(), ItExpr.Is<bool>(disposing => disposing));
        }

        await handler.DisposeAsync();
    }

    [Fact]
    public async Task NoProvider_DiscoveryAndToolCalls_DisposeSeparateHttpClientsAndSessionsAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        DefaultMcpToolHandler handler = new(null, stub.CreateMessageHandler);
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

        await handler.DisposeAsync();
        Assert.Equal(2, stub.Terminations);
    }

    [Fact]
    public async Task NoProvider_DifferentConnectionNames_DoNotRetainSessionsAsync()
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
        Assert.Equal(3, stub.Initializations);
        Assert.Equal(3, stub.Handlers.Count);
        Assert.Equal(3, stub.Terminations);
        await handler.DisposeAsync();
        Assert.Equal(3, stub.Terminations);
    }

    [Fact]
    public async Task NoProvider_DifferentOrigins_KeepRequestConfigurationAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        await using DefaultMcpToolHandler handler = new(null, stub.CreateMessageHandler);
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
    [InlineData(false)]
    [InlineData(true)]
    public async Task NoProvider_FailedInvocation_DoesNotPreventNextInvocationAsync(bool cancel)
    {
        // Arrange
        ProtocolStub stub = new() { FailOperation = !cancel };
        await using DefaultMcpToolHandler handler = new(null, stub.CreateMessageHandler);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));
        using CancellationTokenSource cancellation = CancellationTokenSource.CreateLinkedTokenSource(timeout.Token);
        using SemaphoreSlim started = new(0);
        if (cancel)
        {
            stub.BeforeOperationAsync = async token =>
            {
                started.Release();
                await Task.Delay(Timeout.Infinite, token);
            };
        }

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

        stub.BeforeOperationAsync = null;
        stub.FailOperation = false;
        McpServerToolResultContent result = await InvokeAsync(handler, "ping", timeout.Token);

        // Assert
        Assert.NotNull(result.Outputs);
        Assert.Equal("ok", Assert.IsType<TextContent>(Assert.Single(result.Outputs)).Text);
        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
        Assert.Equal(2, stub.Handlers.Count);
        foreach (Mock<HttpMessageHandler> transport in stub.Handlers)
        {
            transport.Protected().Verify("Dispose", Times.Once(), ItExpr.Is<bool>(disposing => disposing));
        }
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
        await handler.DisposeAsync();

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
    public async Task Factory_InvocationFailure_DisposesClientAndAllowsNextInvocationAsync(bool failInitialization, bool failOperation)
    {
        // Arrange
        ProtocolStub stub = new() { FailInitialization = failInitialization, FailOperation = failOperation };
        using HttpMessageInvoker poolOwner = new(stub.CreateMessageHandler());
        HttpMessageHandler pooledHandler = Assert.Single(stub.Handlers).Object;
        List<HttpClient> clients = [];
        Mock<IHttpClientFactory> factory = new();
        factory.Setup(f => f.CreateClient("workflow-mcp")).Returns(() =>
        {
            HttpClient client = new(pooledHandler, disposeHandler: false);
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

        await using DefaultMcpToolHandler handler = new(factory.Object, "workflow-mcp");
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
        stub.BeforeOperationAsync = null;
        stub.FailInitialization = false;
        stub.FailOperation = false;
        McpServerToolResultContent result = await InvokeAsync(handler, "ping", timeout.Token);

        // Assert
        Assert.NotNull(result.Outputs);
        Assert.Equal("ok", Assert.IsType<TextContent>(Assert.Single(result.Outputs)).Text);
        Assert.Equal(2, clients.Count);
        await Assert.ThrowsAsync<ObjectDisposedException>(() => clients[1].GetAsync(new Uri("https://mcp.example/api"), timeout.Token));
        Assert.Single(stub.Handlers).Protected().Verify("Dispose", Times.Never(), ItExpr.Is<bool>(disposing => disposing));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task DisposeAsync_WaitsForOwnedInvocationCleanupAsync(bool useFactory, bool pauseInitialization)
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

        Mock<IHttpClientFactory> factory = new();
        HttpClient? factoryClient = null;
        factory.Setup(f => f.CreateClient("workflow-mcp")).Returns(() => factoryClient = new(stub.CreateMessageHandler()));
        DefaultMcpToolHandler handler = useFactory
            ? new(factory.Object, "workflow-mcp")
            : new(null, stub.CreateMessageHandler);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        Task<McpServerToolResultContent> invocation = InvokeAsync(handler, "ping", timeout.Token);
        await started.WaitAsync(timeout.Token);
        Task disposal = handler.DisposeAsync().AsTask();
        Assert.False(disposal.IsCompleted);
        await Assert.ThrowsAsync<ObjectDisposedException>(() => InvokeAsync(handler, "ping", timeout.Token));
        Mock<HttpMessageHandler> transport = Assert.Single(stub.Handlers);
        transport.Protected().Verify("Dispose", Times.Never(), ItExpr.Is<bool>(disposing => disposing));
        finish.Release();
        await invocation;
        await disposal;

        // Assert
        Assert.Equal(1, stub.Initializations);
        Assert.Equal(1, stub.Terminations);
        transport.Protected().Verify("Dispose", Times.Once(), ItExpr.Is<bool>(disposing => disposing));
        if (useFactory)
        {
            Assert.NotNull(factoryClient);
            await Assert.ThrowsAsync<ObjectDisposedException>(() => factoryClient.GetAsync(new Uri("https://mcp.example/api"), timeout.Token));
        }
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

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    public async Task ConcurrentInvocations_DoNotCoalesceOrSerializeSessionsAsync(bool useProvider, bool useFactory)
    {
        // Arrange
        ProtocolStub stub = new();
        using HttpClient? client = useProvider ? new(stub.CreateMessageHandler()) : null;
        using ServiceProvider? serviceProvider = useFactory
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
        int providerCalls = 0;
        await using DefaultMcpToolHandler handler = serviceProvider is not null
            ? new(serviceProvider.GetRequiredService<IHttpClientFactory>(), "workflow-mcp")
            : new(useProvider ? (_, _) =>
            {
                Interlocked.Increment(ref providerCalls);
                return Task.FromResult(client);
            }
        : null, stub.CreateMessageHandler);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        Task<McpServerToolResultContent> first = InvokeAsync(handler, "session", timeout.Token);
        Task<McpServerToolResultContent> second = InvokeAsync(handler, "session", timeout.Token);
        await started.WaitAsync(timeout.Token);
        await started.WaitAsync(timeout.Token);
        finish.Release(2);
        McpServerToolResultContent[] results = await Task.WhenAll(first, second);

        // Assert
        Assert.Equal(useProvider ? 2 : 0, providerCalls);
        Assert.Equal(2, stub.Initializations);
        Assert.Equal(2, stub.Terminations);
        IList<AIContent>? firstOutputs = results[0].Outputs;
        IList<AIContent>? secondOutputs = results[1].Outputs;
        Assert.NotNull(firstOutputs);
        Assert.NotNull(secondOutputs);
        Assert.NotEqual(
            Assert.IsType<TextContent>(Assert.Single(firstOutputs)).Text,
            Assert.IsType<TextContent>(Assert.Single(secondOutputs)).Text);
        Assert.Equal(useProvider || useFactory ? 1 : 2, stub.Handlers.Count);
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
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task InitializationFailure_RespectsTransportOwnershipAsync(bool useProvider, bool provideClient)
    {
        // Arrange
        ProtocolStub stub = new() { FailInitialization = true };
        using HttpClient? client = provideClient ? new(stub.CreateMessageHandler()) : null;
        DefaultMcpToolHandler handler = new(
            useProvider ? (_, _) => Task.FromResult(client) : null, stub.CreateMessageHandler);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        await Assert.ThrowsAsync<HttpRequestException>(() => InvokeAsync(handler, "ping", timeout.Token));

        // Assert
        Mock<HttpMessageHandler> transport = Assert.Single(stub.Handlers);
        transport.Protected().Verify("Dispose", provideClient ? Times.Never() : Times.Once(), ItExpr.Is<bool>(disposing => disposing));
        await handler.DisposeAsync();
        transport.Protected().Verify("Dispose", provideClient ? Times.Never() : Times.Once(), ItExpr.Is<bool>(disposing => disposing));
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

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Provider_ReentrantDisposal_ThrowsWithoutStartingShutdownAsync(bool fromChildTask)
    {
        // Arrange
        ProtocolStub stub = new();
        using HttpClient client = new(stub.CreateMessageHandler());
        DefaultMcpToolHandler? handler = null;
        int rejectedDisposals = 0;
        handler = new(async (_, _) =>
        {
            async Task DisposeAsync() => await handler!.DisposeAsync();
            InvalidOperationException error = await Assert.ThrowsAsync<InvalidOperationException>(
                () => fromChildTask ? Task.Run(DisposeAsync) : DisposeAsync());
            Assert.Contains("active MCP invocation", error.Message);
            rejectedDisposals++;
            return client;
        });
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        await InvokeAsync(handler, "ping", timeout.Token);
        await InvokeAsync(handler, "ping", timeout.Token);
        await handler.DisposeAsync();

        // Assert
        Assert.Equal(2, rejectedDisposals);
        Assert.Equal(2, stub.Terminations);
    }

    [Fact]
    public async Task Provider_CompletedInheritedContext_CanDisposeHandlerAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        using HttpClient client = new(stub.CreateMessageHandler());
        using SemaphoreSlim finished = new(0);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));
        Task? inheritedDisposal = null;
        DefaultMcpToolHandler? handler = null;
        handler = new((_, token) =>
        {
            inheritedDisposal = Task.Run(async () =>
            {
                await finished.WaitAsync(token);
                await handler!.DisposeAsync();
            }, token);
            return Task.FromResult<HttpClient?>(client);
        });

        // Act
        await InvokeAsync(handler, "ping", timeout.Token);
        finished.Release();
        await Assert.IsAssignableFrom<Task>(inheritedDisposal);

        // Assert
        Assert.Equal(1, stub.Terminations);
        await Assert.ThrowsAsync<ObjectDisposedException>(() => InvokeAsync(handler, "ping", timeout.Token));
    }

    [Fact]
    public async Task Provider_NestedInvocation_RestoresOuterDisposalGuardAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        using HttpClient client = new(stub.CreateMessageHandler());
        bool nested = false;
        DefaultMcpToolHandler? handler = null;
        handler = new(async (_, token) =>
        {
            if (!nested)
            {
                nested = true;
                await InvokeAsync(handler!, "ping", token);
                await Assert.ThrowsAsync<InvalidOperationException>(() => handler!.DisposeAsync().AsTask());
            }

            return client;
        });
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        await InvokeAsync(handler, "ping", timeout.Token);
        await handler.DisposeAsync();

        // Assert
        Assert.True(nested);
        Assert.Equal(2, stub.Terminations);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Invocation_HttpHandlerCleanupFailure_DoesNotReplaceOutcomeAsync(bool failOperation)
    {
        // Arrange
        ProtocolStub stub = new() { FailOperation = failOperation, FailTransportDisposal = true };
        DefaultMcpToolHandler handler = new(null, stub.CreateMessageHandler);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        using CleanupTraceListener listener = new();
        Trace.Listeners.Add(listener);
        try
        {
            // Act
            if (failOperation)
            {
                await Assert.ThrowsAsync<HttpRequestException>(() => InvokeAsync(handler, "ping", timeout.Token));
            }
            else
            {
                McpServerToolResultContent result = await InvokeAsync(handler, "ping", timeout.Token);
                Assert.NotNull(result.Outputs);
                Assert.Equal("ok", Assert.IsType<TextContent>(Assert.Single(result.Outputs)).Text);
            }

            await handler.DisposeAsync();

            // Assert
            Assert.Equal(1, stub.Terminations);
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

    [Fact]
    public async Task Provider_CompletedNestedContext_StillGuardsActiveOuterInvocationAsync()
    {
        // Arrange
        ProtocolStub stub = new();
        using HttpClient client = new(stub.CreateMessageHandler());
        using SemaphoreSlim nestedFinished = new(0);
        Task? inheritedDisposal = null;
        int providerCalls = 0;
        DefaultMcpToolHandler? handler = null;
        handler = new(async (_, token) =>
        {
            if (++providerCalls == 1)
            {
                await InvokeAsync(handler!, "ping", token);
                nestedFinished.Release();
                await Assert.IsAssignableFrom<Task>(inheritedDisposal);
            }
            else
            {
                inheritedDisposal = Task.Run(async () =>
                {
                    await nestedFinished.WaitAsync(token);
                    await Assert.ThrowsAsync<InvalidOperationException>(() => handler!.DisposeAsync().AsTask());
                }, token);
            }

            return client;
        });
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        // Act
        await InvokeAsync(handler, "ping", timeout.Token);
        await handler.DisposeAsync();

        // Assert
        Assert.Equal(2, providerCalls);
        Assert.Equal(2, stub.Terminations);
    }

    [Fact]
    public async Task InitializationFailure_ReportsHttpHandlerCleanupFailureAsync()
    {
        // Arrange
        ProtocolStub stub = new() { FailInitialization = true, FailTransportDisposal = true };
        DefaultMcpToolHandler handler = new(null, stub.CreateMessageHandler);
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));

        using CleanupTraceListener listener = new();
        Trace.Listeners.Add(listener);
        try
        {
            // Act
            await Assert.ThrowsAsync<HttpRequestException>(() => InvokeAsync(handler, "ping", timeout.Token));
            await handler.DisposeAsync();

            // Assert
            Assert.Contains("Failed to dispose MCP transport", listener.Output);
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
        public Func<CancellationToken, Task>? BeforeInitializationAsync { get; set; }
        public Func<CancellationToken, Task>? BeforeOperationAsync { get; set; }
        public Action<HttpRequestMessage>? OnOperation { get; set; }
        public bool FailInitialization { get; set; }
        public bool FailOperation { get; set; }
        public bool FailTransportDisposal { get; set; }

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
                if (this.BeforeInitializationAsync is not null)
                {
                    await this.BeforeInitializationAsync(cancellationToken);
                }

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

    private sealed class CleanupTraceListener : TraceListener
    {
        private readonly StringBuilder _output = new();

        public string Output => this._output.ToString();

        public override void Write(string? message) => this._output.Append(message);

        public override void WriteLine(string? message) => this._output.AppendLine(message);
    }
}
