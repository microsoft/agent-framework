// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Unit tests for <see cref="DefaultHttpRequestHandler"/>.
/// </summary>
public sealed class DefaultHttpRequestHandlerTests
{
    private static readonly string[] s_setCookieValues = ["a=1", "b=2"];

    private const string TestUrl = "https://api.example.test/resource";

    #region Constructor Tests

    [Fact]
    public void ConstructorWithNullHttpMessageHandlerFactoryThrows()
    {
        // Act
        static void act() => _ = new DefaultHttpRequestHandler([], null!);

        // Assert
        Assert.Throws<ArgumentNullException>(act);
    }

    [Fact]
    public async Task SendAsyncUsesNamedFactoryWithoutDisposingHandlersAsync()
    {
        // Arrange
        using HttpResponseMessage firstResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("ok", Encoding.UTF8, "text/plain"),
        };
        using HttpResponseMessage secondResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("ok", Encoding.UTF8, "text/plain"),
        };
        int requestCount = 0;
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((_, _) =>
            Task.FromResult(requestCount++ == 0 ? firstResponse : secondResponse));
#pragma warning restore CA2025
        Mock<IHttpMessageHandlerFactory> factory = new();
        factory.Setup(f => f.CreateHandler("workflow")).Returns(messageHandler);
        DefaultHttpRequestHandler handler = new(["api.example.test"], factory.Object, "workflow");
        HttpRequestInfo request = new() { Method = "GET", Url = TestUrl };

        // Act
        HttpRequestResult result = await handler.SendAsync(request);
        await handler.SendAsync(request);

        // Assert
        Assert.NotNull(messageHandler.LastRequest);
        Assert.NotNull(messageHandler.LastRequest.RequestUri);
        Assert.Equal(TestUrl, messageHandler.LastRequest.RequestUri.ToString());
        Assert.Equal("ok", result.Body);
        factory.Verify(f => f.CreateHandler("workflow"), Times.Exactly(2));
        Assert.False(messageHandler.IsDisposed);
    }

    [Fact]
    public async Task SendAsyncDoesNotDisposeFactoryHandlerOnFailureAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new((_, _) =>
            throw new HttpRequestException("Transport failed."));
        Mock<IHttpMessageHandlerFactory> factory = new();
        factory.Setup(f => f.CreateHandler(string.Empty)).Returns(messageHandler);
        DefaultHttpRequestHandler handler = new(["api.example.test"], factory.Object);

        // Act
        async Task actAsync() => await handler.SendAsync(new HttpRequestInfo { Url = TestUrl });

        // Assert
        await Assert.ThrowsAsync<HttpRequestException>(actAsync);
        Assert.False(messageHandler.IsDisposed);
    }

    #endregion

    #region Argument Validation Tests

    [Fact]
    public async Task SendAsyncRejectsAutomaticRedirectsBeforeTransportAsync()
    {
        // Arrange
        await using RawHttpServer server = new();
        ServiceCollection services = new();
        services.AddHttpClient();
        using ServiceProvider serviceProvider = services.BuildServiceProvider();
        DefaultHttpRequestHandler handler = new(
            [new Uri(server.Url).Authority], serviceProvider.GetRequiredService<IHttpMessageHandlerFactory>());
        HttpRequestInfo request = new() { Url = server.Url };

        // Act
        Exception? exception = await Record.ExceptionAsync(() => handler.SendAsync(request, TestContext.Current.CancellationToken));
        string? rawRequest = await server.TryReadRequestAsync();

        // Assert
        Assert.IsType<InvalidOperationException>(exception);
        Assert.Null(rawRequest);
    }

    [Theory]
    [InlineData(true, false)]
    [InlineData(false, true)]
    public async Task SendAsyncRejectsInvalidHttpClientHandlerSettingsBeforeTransportAsync(bool allowAutoRedirect, bool useCookies)
    {
        // Arrange
        await using RawHttpServer server = new();
        using HttpClientHandler transport = new()
        {
            AllowAutoRedirect = allowAutoRedirect,
            UseCookies = useCookies,
            CheckCertificateRevocationList = true,
        };
        DefaultHttpRequestHandler handler = new([new Uri(server.Url).Authority], CreateHttpMessageHandlerFactory(transport).Object);

        // Act
        Exception? exception = await Record.ExceptionAsync(() =>
            handler.SendAsync(new HttpRequestInfo { Url = server.Url }, TestContext.Current.CancellationToken));
        string? rawRequest = await server.TryReadRequestAsync();

        // Assert
        Assert.IsType<InvalidOperationException>(exception);
        Assert.Null(rawRequest);
    }

#if NET
    [Theory]
    [InlineData(true, false)]
    [InlineData(false, true)]
    public async Task SendAsyncRejectsInvalidSocketsHttpHandlerSettingsBeforeTransportAsync(bool allowAutoRedirect, bool useCookies)
    {
        // Arrange
        await using RawHttpServer server = new();
        using SocketsHttpHandler transport = new()
        {
            AllowAutoRedirect = allowAutoRedirect,
            UseCookies = useCookies,
        };
        DefaultHttpRequestHandler handler = new([new Uri(server.Url).Authority], CreateHttpMessageHandlerFactory(transport).Object);

        // Act
        Exception? exception = await Record.ExceptionAsync(() =>
            handler.SendAsync(new HttpRequestInfo { Url = server.Url }, TestContext.Current.CancellationToken));
        string? rawRequest = await server.TryReadRequestAsync();

        // Assert
        Assert.IsType<InvalidOperationException>(exception);
        Assert.Null(rawRequest);
    }

    [Fact]
    public async Task SendAsyncAcceptsSocketsHttpHandlerWithRedirectsAndCookiesDisabledAsync()
    {
        // Arrange
        await using RawHttpServer server = new();
        using SocketsHttpHandler transport = new()
        {
            AllowAutoRedirect = false,
            UseCookies = false,
        };
        DefaultHttpRequestHandler handler = new([new Uri(server.Url).Authority], CreateHttpMessageHandlerFactory(transport).Object);

        // Act
        HttpRequestResult result = await handler.SendAsync(new HttpRequestInfo { Url = server.Url }, TestContext.Current.CancellationToken);

        // Assert
        Assert.Equal("ok", result.Body);
    }
#endif

    [Fact]
    public async Task SendAsyncWithoutAllowedHostsRejectsBeforeTransportAsync()
    {
        // Arrange
        Mock<IHttpMessageHandlerFactory> factory = new(MockBehavior.Strict);
        using TestHttpMessageHandler messageHandler = new((_, _) =>
            Task.FromException<HttpResponseMessage>(new InvalidOperationException("Unexpected HTTP request.")));
        using HttpClient client = new(messageHandler);
        DefaultHttpRequestHandler handler = new([], factory.Object);
        HttpRequestInfo request = new() { Url = TestUrl };

        // Act
        async Task actAsync() => await handler.SendAsync(request, TestContext.Current.CancellationToken);

        // Assert
        await Assert.ThrowsAsync<HttpRequestException>(actAsync);
        factory.VerifyNoOtherCalls();
        Assert.Null(messageHandler.LastRequest);
    }

    [Theory]
    [InlineData("Host", "other.example.test")]
    [InlineData("hOsT", "api.example.test")]
    public async Task SendAsyncRejectsWorkflowHostHeaderBeforeFactoryAsync(string headerName, string headerValue)
    {
        // Arrange
        Mock<IHttpMessageHandlerFactory> factory = new(MockBehavior.Strict);
        using TestHttpMessageHandler messageHandler = new((_, _) =>
            Task.FromException<HttpResponseMessage>(new InvalidOperationException("Unexpected HTTP request.")));
        using HttpClient client = new(messageHandler);
        DefaultHttpRequestHandler handler = new(["api.example.test"], factory.Object);
        HttpRequestInfo request = new()
        {
            Url = TestUrl,
            Headers = new Dictionary<string, string> { [headerName] = headerValue },
        };

        // Act
        async Task actAsync() => await handler.SendAsync(request, TestContext.Current.CancellationToken);

        // Assert
        await Assert.ThrowsAsync<HttpRequestException>(actAsync);
        factory.VerifyNoOtherCalls();
        Assert.Null(messageHandler.LastRequest);
    }

    [Fact]
    public async Task SendAsyncRejectsUnsupportedPrimaryHandlerBeforeTransportAsync()
    {
        // Arrange
        using HttpMessageHandler messageHandler = Mock.Of<HttpMessageHandler>();
        Mock<IHttpMessageHandlerFactory> factory = CreateHttpMessageHandlerFactory(messageHandler);
        DefaultHttpRequestHandler handler = new(["api.example.test"], factory.Object);
        HttpRequestInfo request = new() { Url = TestUrl };

        // Act
        async Task actAsync() => await handler.SendAsync(request, TestContext.Current.CancellationToken);

        // Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(actAsync);
        Assert.Contains("supported primary HTTP handler", exception.Message, StringComparison.Ordinal);
        Assert.Contains("HttpClientHandler", exception.Message, StringComparison.Ordinal);
#if NET
        Assert.Contains("SocketsHttpHandler", exception.Message, StringComparison.Ordinal);
#else
        Assert.DoesNotContain("SocketsHttpHandler", exception.Message, StringComparison.Ordinal);
#endif
    }

    [Fact]
    public async Task SendAsyncRejectsIncompletePipelineBeforeTransportAsync()
    {
        // Arrange
        using DelegatingHandler messageHandler = Mock.Of<DelegatingHandler>();
        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        // Act
        async Task actAsync() => await handler.SendAsync(new HttpRequestInfo { Url = TestUrl }, TestContext.Current.CancellationToken);

        // Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(actAsync);
        Assert.Contains("must have a primary handler", exception.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SendAsyncRejectsCyclicPipelineBeforeTransportAsync(bool multipleHandlers)
    {
        // Arrange
        using HttpMessageHandler primary = Mock.Of<HttpMessageHandler>();
        using DelegatingHandler first = new Mock<DelegatingHandler> { CallBase = true }.Object;
        using DelegatingHandler second = new Mock<DelegatingHandler> { CallBase = true }.Object;
        first.InnerHandler = multipleHandlers ? second : first;
        second.InnerHandler = first;
        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(first).Object);

        // Act
        Task<Exception?> invocation = Task.Run(async () => await Record.ExceptionAsync(() =>
            handler.SendAsync(new HttpRequestInfo { Url = TestUrl }, TestContext.Current.CancellationToken)));
        try
        {
            // Assert
            Task completed = await Task.WhenAny(invocation, Task.Delay(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken));
            Assert.True(ReferenceEquals(invocation, completed), "Cyclic pipeline validation did not complete.");
            InvalidOperationException exception = Assert.IsType<InvalidOperationException>(await invocation);
            Assert.Contains("cycle", exception.Message, StringComparison.Ordinal);
        }
        finally
        {
            // Break the cycle before disposing the handlers.
            first.InnerHandler = primary;
            second.InnerHandler = primary;
            await invocation;
        }
    }

    [Fact]
    public async Task SendAsyncWithNullRequestThrowsAsync()
    {
        // Arrange
        using ServiceProvider serviceProvider = CreateServiceProvider();
        DefaultHttpRequestHandler handler = new(["api.example.test"], serviceProvider.GetRequiredService<IHttpMessageHandlerFactory>());

        // Act
        async Task actAsync() => await handler.SendAsync(null!);

        // Assert
        await Assert.ThrowsAsync<ArgumentNullException>(actAsync);
    }

    [Fact]
    public async Task SendAsyncWithEmptyUrlThrowsAsync()
    {
        // Arrange
        using ServiceProvider serviceProvider = CreateServiceProvider();
        DefaultHttpRequestHandler handler = new(["api.example.test"], serviceProvider.GetRequiredService<IHttpMessageHandlerFactory>());
        HttpRequestInfo request = new() { Method = "GET", Url = "" };

        // Act
        async Task actAsync() => await handler.SendAsync(request);

        // Assert
        await Assert.ThrowsAsync<ArgumentException>(actAsync);
    }

    [Fact]
    public async Task SendAsyncWithEmptyMethodThrowsAsync()
    {
        // Arrange
        using ServiceProvider serviceProvider = CreateServiceProvider();
        DefaultHttpRequestHandler handler = new(["api.example.test"], serviceProvider.GetRequiredService<IHttpMessageHandlerFactory>());
        HttpRequestInfo request = new() { Method = "", Url = TestUrl };

        // Act
        async Task actAsync() => await handler.SendAsync(request);

        // Assert
        await Assert.ThrowsAsync<ArgumentException>(actAsync);
    }

    [Fact]
    public async Task SendAsyncWithoutAllowedHostsDoesNotConnectAsync()
    {
        // Arrange
        await using RawHttpServer server = new();
        using ServiceProvider serviceProvider = CreateServiceProvider();
        DefaultHttpRequestHandler handler = new([], serviceProvider.GetRequiredService<IHttpMessageHandlerFactory>());
        HttpRequestInfo request = new() { Method = "GET", Url = server.Url };

        // Act
        async Task actAsync() => await handler.SendAsync(request, TestContext.Current.CancellationToken);

        // Assert
        await Assert.ThrowsAsync<HttpRequestException>(actAsync);
        Assert.Null(await server.TryReadRequestAsync());
    }

    [Theory]
    [InlineData("api.example.test", "https://API.EXAMPLE.TEST/resource")]
    [InlineData("API.EXAMPLE.TEST.", "https://api.example.test/resource")]
    [InlineData("api.example.test", "https://api.example.test./resource")]
    [InlineData("b\u00fccher.example", "https://xn--bcher-kva.example/resource")]
    [InlineData("xn--bcher-kva.example", "https://b\u00fccher.example/resource")]
    [InlineData("api.example.test", "https://api.example.test:443/resource")]
    [InlineData("api.example.test:443", "https://api.example.test/resource")]
    [InlineData("api.example.test:1", "https://api.example.test:1/resource")]
    [InlineData("api.example.test:65535", "https://api.example.test:65535/resource")]
    [InlineData("api.example.test", "http://api.example.test:443/resource")]
    [InlineData("API.EXAMPLE.TEST.:8443", "https://api.example.test:8443/resource")]
    [InlineData("api.example.test:80", "http://api.example.test/resource")]
    [InlineData("b\u00fccher.example:8443", "https://xn--bcher-kva.example:8443/resource")]
    [InlineData("127.0.0.1", "https://127.1/resource")]
    [InlineData("10.0.0.1:8080", "http://10.0.0.1:8080/resource")]
    [InlineData("::1", "https://[::1]/resource")]
    [InlineData("[::1]", "https://[::1]:443/resource")]
    [InlineData("[::1]:8080", "http://[::1]:8080/resource")]
    [InlineData("[2001:db8::1]:8443", "https://[2001:db8::1]:8443/resource")]
    public async Task SendAsyncAllowsExactConfiguredHostAsync(string allowedHost, string url)
    {
        // Arrange
        using HttpResponseMessage response = new(HttpStatusCode.OK);
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((_, _) => Task.FromResult(response));
#pragma warning restore CA2025
        using HttpClient client = new(messageHandler);
        DefaultHttpRequestHandler handler = new([allowedHost], CreateHttpMessageHandlerFactory(messageHandler).Object);

        // Act
        HttpRequestResult result = await handler.SendAsync(new HttpRequestInfo { Url = url });

        // Assert
        Assert.True(result.IsSuccessStatusCode);
        Assert.NotNull(messageHandler.LastRequest);
    }

    [Theory]
    [InlineData("https://other.example.test/")]
    [InlineData("https://sub.api.example.test/")]
    [InlineData("https://api.example.test.other.test/")]
    [InlineData("https://api.example.test@other.test/")]
    [InlineData("http://127.0.0.1/")]
    public async Task SendAsyncRejectsUnlistedHostBeforeFactoryAsync(string url)
    {
        // Arrange
        Mock<IHttpMessageHandlerFactory> factory = new(MockBehavior.Strict);
        DefaultHttpRequestHandler handler = new(["api.example.test"], factory.Object);

        // Act
        async Task actAsync() => await handler.SendAsync(new HttpRequestInfo { Url = url });

        // Assert
        await Assert.ThrowsAsync<HttpRequestException>(actAsync);
        factory.VerifyNoOtherCalls();
    }

    [Theory]
    [InlineData("api.example.test", "http://api.example.test/")]
    [InlineData("api.example.test", "https://api.example.test:8443/")]
    [InlineData("api.example.test:8443", "https://api.example.test/")]
    [InlineData("api.example.test:8443", "https://api.example.test:8080/")]
    [InlineData("::1", "http://[::1]/")]
    [InlineData("[::1]:8443", "https://[::1]/")]
    public async Task SendAsyncRejectsUnlistedPortBeforeFactoryAsync(string allowedHost, string url)
    {
        // Arrange
        Mock<IHttpMessageHandlerFactory> factory = new(MockBehavior.Strict);
        using TestHttpMessageHandler messageHandler = new((_, _) =>
            Task.FromException<HttpResponseMessage>(new InvalidOperationException("Unexpected HTTP request.")));
        using HttpClient client = new(messageHandler);
        DefaultHttpRequestHandler handler = new([allowedHost], factory.Object);

        // Act
        async Task actAsync() => await handler.SendAsync(new HttpRequestInfo { Url = url });

        // Assert
        await Assert.ThrowsAsync<HttpRequestException>(actAsync);
        factory.VerifyNoOtherCalls();
        Assert.Null(messageHandler.LastRequest);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("*.example.test")]
    [InlineData("https://api.example.test")]
    [InlineData("api.example.test:")]
    [InlineData("api.example.test:abc")]
    [InlineData("api.example.test:0")]
    [InlineData("api.example.test:-1")]
    [InlineData("api.example.test:+443")]
    [InlineData("api.example.test:65536")]
    [InlineData("api.example.test:999999999999")]
    [InlineData("api.example.test:443/path")]
    [InlineData("[::1]:")]
    [InlineData("[::1]:65536")]
    [InlineData("::1:00443")]
    [InlineData("api.example.test/path")]
    [InlineData("api.example.test?query")]
    [InlineData("user@api.example.test")]
    public void ConstructorRejectsInvalidAllowedHost(string? host)
    {
        // Act
        void act() => _ = new DefaultHttpRequestHandler([host!], Mock.Of<IHttpMessageHandlerFactory>());

        // Assert
        Assert.Throws<ArgumentException>(act);
    }

    [Fact]
    public void ConstructorRejectsNullAllowlist()
    {
        // Act
        static void act() => _ = new DefaultHttpRequestHandler(allowedHosts: null!, Mock.Of<IHttpMessageHandlerFactory>());

        // Assert
        Assert.Throws<ArgumentNullException>(act);
    }

    [Fact]
    public async Task SendAsyncUsesAllowlistSnapshotAsync()
    {
        // Arrange
        List<string> allowedHosts = ["api.example.test"];
        DefaultHttpRequestHandler handler = new(allowedHosts, Mock.Of<IHttpMessageHandlerFactory>());
        allowedHosts.Add("other.example.test");

        // Act
        async Task actAsync() => await handler.SendAsync(new HttpRequestInfo { Url = "https://other.example.test/" });

        // Assert
        await Assert.ThrowsAsync<HttpRequestException>(actAsync);
    }

    [Theory]
    [InlineData("https://other.example.test/next")]
    [InlineData("https://api.example.test:8443/next")]
    public async Task SendAsyncRejectsUnlistedRedirectBeforeFactoryAsync(string redirectUrl)
    {
        // Arrange
        using HttpResponseMessage redirectResponse = new(HttpStatusCode.Found)
        {
            Headers = { Location = new Uri(redirectUrl) },
        };
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((_, _) => Task.FromResult(redirectResponse));
#pragma warning restore CA2025
        Mock<IHttpMessageHandlerFactory> factory = CreateHttpMessageHandlerFactory(messageHandler);
        DefaultHttpRequestHandler handler = new(["api.example.test"], factory.Object);

        // Act
        async Task actAsync() => await handler.SendAsync(new HttpRequestInfo { Url = TestUrl });

        // Assert
        await Assert.ThrowsAsync<HttpRequestException>(actAsync);
        factory.Verify(f => f.CreateHandler(string.Empty), Times.Once);
        Assert.Single(messageHandler.RequestMethods);
    }

    [Fact]
    public async Task SendAsyncAllowsExplicitlyConfiguredRedirectPortAsync()
    {
        // Arrange
        List<string> requestUrls = [];
        using HttpResponseMessage redirectResponse = new(HttpStatusCode.Found)
        {
            Headers = { Location = new Uri("https://api.example.test:8443/next") },
        };
        using HttpResponseMessage okResponse = new(HttpStatusCode.OK);
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((request, _) =>
        {
            requestUrls.Add(request.RequestUri!.ToString());
            return Task.FromResult(requestUrls.Count == 1 ? redirectResponse : okResponse);
        });
#pragma warning restore CA2025
        DefaultHttpRequestHandler handler = new(
            ["api.example.test", "api.example.test:8443"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        // Act
        HttpRequestResult result = await handler.SendAsync(new HttpRequestInfo { Url = TestUrl });

        // Assert
        Assert.True(result.IsSuccessStatusCode);
        Assert.Equal([TestUrl, "https://api.example.test:8443/next"], requestUrls);
        Assert.Equal(2, messageHandler.RequestMethods.Count);
    }

    [Theory]
    [InlineData("file:///resource")]
    [InlineData("ftp://api.example.test/resource")]
    public async Task SendAsyncRejectsNonHttpSchemeAsync(string url)
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new((_, _) =>
            Task.FromException<HttpResponseMessage>(new InvalidOperationException("Unexpected HTTP request.")));
        using HttpClient client = new(messageHandler);
        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        // Act
        async Task actAsync() => await handler.SendAsync(new HttpRequestInfo { Url = url });

        // Assert
        await Assert.ThrowsAsync<HttpRequestException>(actAsync);
        Assert.Null(messageHandler.LastRequest);
    }

    [Fact]
    public async Task SendAsyncWithFactoryClientAllowsConfiguredLocalHostAsync()
    {
        // Arrange
        await using RawHttpServer server = new();
        using ServiceProvider serviceProvider = CreateServiceProvider();
        DefaultHttpRequestHandler handler = new([new Uri(server.Url).Authority], serviceProvider.GetRequiredService<IHttpMessageHandlerFactory>());

        // Act
        HttpRequestResult result = await handler.SendAsync(new HttpRequestInfo { Url = server.Url }, TestContext.Current.CancellationToken);

        // Assert
        Assert.True(result.IsSuccessStatusCode);
        Assert.NotNull(await server.TryReadRequestAsync());
    }

    #endregion

    #region Send Behavior Tests

    [Fact]
    public async Task SendAsyncUsesFactoryHttpClientAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("hello", Encoding.UTF8, "text/plain"),
            }));

        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        HttpRequestInfo request = new() { Method = "GET", Url = TestUrl };

        // Act
        HttpRequestResult result = await handler.SendAsync(request);

        // Assert
        Assert.NotNull(messageHandler.LastRequest);
        Assert.Equal(HttpMethod.Get, messageHandler.LastRequest!.Method);
        Assert.Equal(TestUrl, messageHandler.LastRequest.RequestUri!.ToString());
        Assert.Equal(200, result.StatusCode);
        Assert.True(result.IsSuccessStatusCode);
        Assert.Equal("hello", result.Body);
    }

    [Fact]
    public async Task SendAsyncMapsAllKnownMethodsAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)));

        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        foreach (string method in new[] { "GET", "POST", "PUT", "PATCH", "DELETE", "CUSTOM" })
        {
            HttpRequestInfo request = new() { Method = method, Url = TestUrl };

            // Act
            await handler.SendAsync(request);

            // Assert
            Assert.Equal(method, messageHandler.LastRequest!.Method.Method);
        }
    }

    [Fact]
    public async Task SendAsyncNormalizesWhitespaceAroundCustomMethodAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)));
        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);
        HttpRequestInfo request = new() { Method = "  custom  ", Url = TestUrl };

        // Act
        await handler.SendAsync(request);

        // Assert - fallback path should apply the same Trim/ToUpperInvariant normalization.
        Assert.Equal("CUSTOM", messageHandler.LastRequest!.Method.Method);
    }

    [Fact]
    public async Task SendAsyncAppliesBodyAndContentTypeAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)));

        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        HttpRequestInfo request = new()
        {
            Method = "POST",
            Url = TestUrl,
            Body = "{\"hello\":\"world\"}",
            BodyContentType = "application/json",
        };

        // Act
        await handler.SendAsync(request);

        // Assert
        Assert.Equal("{\"hello\":\"world\"}", messageHandler.LastRequestBody);
        Assert.Equal("application/json", messageHandler.LastRequestContentType);
    }

    [Fact]
    public async Task SendAsyncAppliesRequestHeadersAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)));

        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
            Headers = new Dictionary<string, string>
            {
                ["Authorization"] = "Bearer secret",
                ["Accept"] = "application/json",
            },
        };

        // Act
        await handler.SendAsync(request);

        // Assert
        Assert.Equal("Bearer secret", messageHandler.LastRequest!.Headers.Authorization!.ToString());
        Assert.Contains(messageHandler.LastRequest.Headers.Accept, mediaType => mediaType.MediaType == "application/json");
    }

    [Fact]
    public async Task SendAsyncRejectsHeaderValuesContainingCrlfBeforeSendingAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        await using RawHttpServer server = new();
        using HttpClientHandler messageHandler = new() { AllowAutoRedirect = false, UseCookies = false, CheckCertificateRevocationList = true };
        DefaultHttpRequestHandler handler = new(["api.example.test", new Uri(server.Url).Authority], CreateHttpMessageHandlerFactory(messageHandler).Object);
        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = server.Url,
            Headers = new Dictionary<string, string>
            {
                ["X-User-Note"] = "safe\r\n\r\nDELETE /admin HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
            },
        };

        // Act
        Exception? exception = await Record.ExceptionAsync(() => handler.SendAsync(request, cancellationToken));
        string? rawRequest = await server.TryReadRequestAsync();

        // Assert
        Assert.Null(rawRequest);
        Assert.IsType<ArgumentException>(exception);
    }

    [Fact]
    public async Task SendAsyncRejectsBodyContentTypeContainingCrlfBeforeSendingAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new((_, _) =>
            throw new InvalidOperationException("The request should be rejected before transport."));
        DefaultHttpRequestHandler handler = new(["api.example.test", "127.0.0.1"], CreateHttpMessageHandlerFactory(messageHandler).Object);
        HttpRequestInfo request = new()
        {
            Method = "POST",
            Url = TestUrl,
            Body = "safe",
            BodyContentType = "text/plain\r\nX-Injected: value",
        };

        // Act
        async Task actAsync() => await handler.SendAsync(request);

        // Assert
        await Assert.ThrowsAsync<ArgumentException>(actAsync);
        Assert.Null(messageHandler.LastRequest);
    }

    [Fact]
    public async Task SendAsyncRoutesContentHeadersToBodyAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)));

        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        HttpRequestInfo request = new()
        {
            Method = "POST",
            Url = TestUrl,
            Body = "raw",
            BodyContentType = "text/plain",
            Headers = new Dictionary<string, string>
            {
                ["Content-Language"] = "en-US",
            },
        };

        // Act
        await handler.SendAsync(request);

        // Assert
        Assert.Contains("en-US", messageHandler.LastRequest!.Content!.Headers.ContentLanguage);
    }

    [Fact]
    public async Task SendAsyncCapturesResponseHeadersAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new((req, _) =>
        {
#pragma warning disable CA2025
            HttpResponseMessage response = new(HttpStatusCode.OK)
            {
                Content = new StringContent("ok", Encoding.UTF8, "text/plain"),
            };
            response.Headers.Add("X-Request-Id", "request-1");
            response.Headers.Add("Set-Cookie", s_setCookieValues);
            return Task.FromResult(response);
#pragma warning restore CA2025
        });

        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        HttpRequestInfo request = new() { Method = "GET", Url = TestUrl };

        // Act
        HttpRequestResult result = await handler.SendAsync(request);

        // Assert
        Assert.NotNull(result.Headers);
        Assert.Contains("X-Request-Id", result.Headers!);
        Assert.Equivalent(s_setCookieValues, result.Headers!["Set-Cookie"]);
        // Content headers also flattened in.
        Assert.Contains("Content-Type", result.Headers!);
    }

    [Fact]
    public async Task SendAsyncFactoryClientDoesNotForwardResponseCookiesToRedirectAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        await using CookieCaptureServer server = new();
        using ServiceProvider serviceProvider = CreateServiceProvider();
        DefaultHttpRequestHandler handler = new([new Uri(server.SetCookieRedirectUrl).Authority], serviceProvider.GetRequiredService<IHttpMessageHandlerFactory>());
        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = server.SetCookieRedirectUrl,
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);
        IReadOnlyList<string> requests = await server.ReadRequestsAsync(TimeSpan.FromSeconds(5));

        // Assert
        Assert.Equal("no-cookie", result.Body);
        Assert.Equal(2, requests.Count);
        Assert.Contains("GET /set-cookie-redirect ", requests[0], StringComparison.Ordinal);
        Assert.Contains("GET /read-cookie ", requests[1], StringComparison.Ordinal);
        Assert.DoesNotContain("Cookie: backend-session=victim-session", requests[1], StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task SendAsyncFactoryClientDoesNotPersistResponseCookiesAcrossRequestsAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        await using CookieCaptureServer server = new();
        using ServiceProvider serviceProvider = CreateServiceProvider();
        DefaultHttpRequestHandler handler = new([new Uri(server.SetCookieUrl).Authority], serviceProvider.GetRequiredService<IHttpMessageHandlerFactory>());
        HttpRequestInfo victimRequest = new()
        {
            Method = "GET",
            Url = server.SetCookieUrl,
        };

        HttpRequestInfo attackerRequest = new()
        {
            Method = "GET",
            Url = server.ReadCookieUrl,
        };

        // Act
        HttpRequestResult victimResult = await handler.SendAsync(victimRequest, cancellationToken);
        HttpRequestResult attackerResult = await handler.SendAsync(attackerRequest, cancellationToken);
        IReadOnlyList<string> requests = await server.ReadRequestsAsync(TimeSpan.FromSeconds(5));

        // Assert
        Assert.Equal("victim", victimResult.Body);
        Assert.Equal("no-cookie", attackerResult.Body);
        Assert.Equal(2, requests.Count);
        Assert.DoesNotContain("Cookie: backend-session=victim-session", requests[1], StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task SendAsyncReturnsFailureStatusWithoutThrowingAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.BadRequest)
            {
                Content = new StringContent("bad request", Encoding.UTF8, "text/plain"),
            }));

        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        HttpRequestInfo request = new() { Method = "GET", Url = TestUrl };

        // Act
        HttpRequestResult result = await handler.SendAsync(request);

        // Assert
        Assert.False(result.IsSuccessStatusCode);
        Assert.Equal(400, result.StatusCode);
        Assert.Equal("bad request", result.Body);
    }

    [Fact]
    public async Task SendAsyncHonorsTimeoutLongerThanDefaultClientTimeoutAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new(async (_, cancellationToken) =>
        {
            // Return headers after HttpClient's default 100-second timeout.
            await Task.Delay(TimeSpan.FromSeconds(101), cancellationToken).ConfigureAwait(false);
            return new HttpResponseMessage(HttpStatusCode.OK);
        });
        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);
        HttpRequestInfo request = new()
        {
            Url = TestUrl,
            Timeout = TimeSpan.FromMinutes(3),
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, TestContext.Current.CancellationToken);

        // Assert
        Assert.Equal(200, result.StatusCode);
    }

    [Fact]
    public async Task SendAsyncTimeoutCancelsRequestAsync()
    {
        // Arrange
        using TestHttpMessageHandler messageHandler = new(async (req, ct) =>
        {
            await Task.Delay(TimeSpan.FromSeconds(5), ct).ConfigureAwait(false);
            return new HttpResponseMessage(HttpStatusCode.OK);
        });

        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
            Timeout = TimeSpan.FromMilliseconds(50),
        };

        // Act
        async Task actAsync() => await handler.SendAsync(request);

        // Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(actAsync);
    }

    [Fact]
    public async Task SendAsyncTimeoutCancelsResponseBodyReadAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        int requestCount = 0;
        using var response = new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StallingContent(),
        };
        using TestHttpMessageHandler messageHandler = new((_, _) =>
        {
            requestCount++;
#pragma warning disable CA2025 // Do not pass 'IDisposable' instances into unawaited tasks
            return Task.FromResult(response);
#pragma warning restore CA2025 // Do not pass 'IDisposable' instances into unawaited tasks
        });

        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);
        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
            Timeout = TimeSpan.FromMilliseconds(50),
        };

        // Act
        async Task actAsync() => await handler.SendAsync(request, cancellationToken);

        // Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(actAsync);
        Assert.Equal(1, requestCount);
    }

    [Fact]
    public async Task SendAsyncTimeoutAppliesAcrossRedirectsAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        int requestCount = 0;
        using HttpResponseMessage redirectResponse = new(HttpStatusCode.TemporaryRedirect)
        {
            Headers = { Location = new Uri("https://api.example.test/next") },
        };
        using HttpResponseMessage okResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("ok", Encoding.UTF8, "text/plain"),
        };
        using TestHttpMessageHandler messageHandler = new(async (req, ct) =>
        {
            requestCount++;
            TimeSpan delay = requestCount == 1 ? TimeSpan.FromMilliseconds(1) : TimeSpan.FromSeconds(5);
            await Task.Delay(delay, ct).ConfigureAwait(false);

            if (requestCount == 1)
            {
                return redirectResponse;
            }

            return okResponse;
        });

        DefaultHttpRequestHandler handler = CreateHandlerWithMessageHandler(messageHandler);
        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
            Timeout = TimeSpan.FromMilliseconds(300),
        };

        // Act
        async Task actAsync() => await handler.SendAsync(request, cancellationToken);

        // Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(actAsync);
        Assert.Equal(2, requestCount);
    }

    [Fact]
    public async Task SendAsyncPostFoundRedirectRewritesToGetAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        using HttpResponseMessage redirectResponse = new(HttpStatusCode.Found)
        {
            Headers = { Location = new Uri("https://api.example.test/next") },
        };
        using HttpResponseMessage okResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("redirected", Encoding.UTF8, "text/plain"),
        };
        int requestCount = 0;
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((_, _) =>
        {
            requestCount++;
            return Task.FromResult(requestCount == 1 ? redirectResponse : okResponse);
        });
#pragma warning restore CA2025

        DefaultHttpRequestHandler handler = CreateHandlerWithMessageHandler(messageHandler);
        HttpRequestInfo request = new()
        {
            Method = "POST",
            Url = TestUrl,
            Body = "request-body",
            BodyContentType = "text/plain",
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);

        // Assert
        Assert.Equal("redirected", result.Body);
        Assert.Equal(["POST", "GET"], messageHandler.RequestMethods);
        Assert.Equal(["request-body", null], messageHandler.RequestBodies);
    }

    [Theory]
    [InlineData(307)]
    [InlineData(308)]
    public async Task SendAsyncPostPreserveMethodRedirectPreservesBodyAsync(int redirectStatusCode)
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        using HttpResponseMessage redirectResponse = new((HttpStatusCode)redirectStatusCode)
        {
            Headers = { Location = new Uri("https://api.example.test/next") },
        };
        using HttpResponseMessage okResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("redirected", Encoding.UTF8, "text/plain"),
        };
        int requestCount = 0;
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            requestCount++;
            return Task.FromResult(requestCount == 1 ? redirectResponse : okResponse);
        });
#pragma warning restore CA2025

        DefaultHttpRequestHandler handler = CreateHandlerWithMessageHandler(messageHandler);
        HttpRequestInfo request = new()
        {
            Method = "POST",
            Url = TestUrl,
            Body = "request-body",
            BodyContentType = "text/plain",
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);

        // Assert
        Assert.Equal("redirected", result.Body);
        Assert.Equal(["POST", "POST"], messageHandler.RequestMethods);
        Assert.Equal(["request-body", "request-body"], messageHandler.RequestBodies);
    }

    [Theory]
    [InlineData(307)]
    [InlineData(308)]
    public async Task SendAsyncPostPreserveMethodRedirectToDifferentOriginWithBodyThrowsAsync(int redirectStatusCode)
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        int requestCount = 0;
        using HttpResponseMessage redirectResponse = new((HttpStatusCode)redirectStatusCode)
        {
            Headers = { Location = new Uri("https://secondary.example.test/next") },
        };
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((_, _) =>
        {
            requestCount++;
            return Task.FromResult(redirectResponse);
        });
#pragma warning restore CA2025

        DefaultHttpRequestHandler handler = CreateHandlerWithMessageHandler(messageHandler);
        HttpRequestInfo request = new()
        {
            Method = "POST",
            Url = TestUrl,
            Body = "request-body",
            BodyContentType = "text/plain",
        };

        // Act
        async Task actAsync() => await handler.SendAsync(request, cancellationToken);

        // Assert
        HttpRequestException exception = await Assert.ThrowsAsync<HttpRequestException>(actAsync);
        Assert.Contains("preserve the request body to a different origin", exception.Message, StringComparison.Ordinal);
        Assert.Equal(1, requestCount);
    }

    [Fact]
    public async Task SendAsyncTooManyRedirectsThrowsAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        int requestCount = 0;
        List<HttpResponseMessage> createdResponses = [];
        using TestHttpMessageHandler messageHandler = new((_, _) =>
        {
            requestCount++;
            HttpResponseMessage response = new(HttpStatusCode.TemporaryRedirect)
            {
                Headers = { Location = new Uri($"https://api.example.test/redirect/{requestCount}") },
            };

            createdResponses.Add(response);
#pragma warning disable CA2025
            return Task.FromResult(response);
#pragma warning restore CA2025
        });

        try
        {
            DefaultHttpRequestHandler handler = CreateHandlerWithMessageHandler(messageHandler);
            HttpRequestInfo request = new()
            {
                Method = "GET",
                Url = TestUrl,
            };

            // Act
            async Task actAsync() => await handler.SendAsync(request, cancellationToken);

            // Assert
            HttpRequestException exception = await Assert.ThrowsAsync<HttpRequestException>(actAsync);
            Assert.Contains("maximum number of HTTP redirects", exception.Message, StringComparison.Ordinal);
            Assert.Equal(51, requestCount);
        }
        finally
        {
            foreach (HttpResponseMessage response in createdResponses)
            {
                response.Dispose();
            }
        }
    }

    [Fact]
    public async Task SendAsyncDoesNotApplyRequestHeadersToRedirectedEndpointAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        List<bool> requestsWithHeader = [];
        using HttpResponseMessage redirectResponse = new(HttpStatusCode.TemporaryRedirect)
        {
            Headers = { Location = new Uri("https://api.example.test/next") },
        };
        using HttpResponseMessage okResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("redirected", Encoding.UTF8, "text/plain"),
        };
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            requestsWithHeader.Add(req.Headers.Contains("X-Trace-Id"));
            if (requestsWithHeader.Count == 1)
            {
                return Task.FromResult(redirectResponse);
            }

            return Task.FromResult(okResponse);
        });
#pragma warning restore CA2025

        DefaultHttpRequestHandler handler = CreateHandlerWithMessageHandler(messageHandler);
        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
            Headers = new Dictionary<string, string>
            {
                ["X-Trace-Id"] = "trace-1",
            },
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);

        // Assert
        Assert.Equal("redirected", result.Body);
        Assert.Equal([true, false], requestsWithHeader);
    }

    [Fact]
    public async Task SendAsyncDoesNotApplyRequestHeadersToDifferentRedirectedEndpointAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        List<bool> requestsWithHeader = [];
        List<string> requestUrls = [];
        using HttpResponseMessage redirectResponse = new(HttpStatusCode.TemporaryRedirect)
        {
            Headers = { Location = new Uri("https://secondary.example.test/next") },
        };
        using HttpResponseMessage okResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("redirected", Encoding.UTF8, "text/plain"),
        };
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            requestUrls.Add(req.RequestUri!.ToString());
            requestsWithHeader.Add(req.Headers.Contains("X-Trace-Id"));
            return Task.FromResult(requestUrls.Count == 1 ? redirectResponse : okResponse);
        });
#pragma warning restore CA2025

        DefaultHttpRequestHandler handler = CreateHandlerWithMessageHandler(messageHandler);

        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
            Headers = new Dictionary<string, string>
            {
                ["X-Trace-Id"] = "trace-1",
            },
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);

        // Assert
        Assert.Equal("redirected", result.Body);
        Assert.Equal([true, false], requestsWithHeader);
        Assert.Equal([TestUrl, "https://secondary.example.test/next"], requestUrls);
    }

    [Fact]
    public async Task SendAsyncDoesNotReadRedirectedResponseBodyAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        TrackingContent redirectedContent = new("not returned");
        using HttpResponseMessage redirectResponse = new(HttpStatusCode.TemporaryRedirect)
        {
            Content = redirectedContent,
            Headers = { Location = new Uri("https://api.example.test/next") },
        };
        using HttpResponseMessage okResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("redirected", Encoding.UTF8, "text/plain"),
        };
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            if (req.RequestUri!.AbsolutePath == "/resource")
            {
                return Task.FromResult(redirectResponse);
            }

            return Task.FromResult(okResponse);
        });
#pragma warning restore CA2025

        DefaultHttpRequestHandler handler = CreateHandlerWithMessageHandler(messageHandler);
        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);

        // Assert
        Assert.Equal("redirected", result.Body);
        Assert.False(redirectedContent.WasRead);
    }

    [Fact]
    public async Task SendAsyncRejectsHttpsToHttpRedirectAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        int requestCount = 0;
        using HttpResponseMessage redirectResponse = new(HttpStatusCode.TemporaryRedirect)
        {
            Headers = { Location = new Uri("http://api.example.test/next") },
        };
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            requestCount++;
            return Task.FromResult(redirectResponse);
        });
#pragma warning restore CA2025

        DefaultHttpRequestHandler handler = CreateHandlerWithMessageHandler(messageHandler);
        HttpRequestInfo request = new()
        {
            Method = "POST",
            Url = TestUrl,
            Body = "request-body",
            BodyContentType = "text/plain",
        };

        // Act
        async Task actAsync() => await handler.SendAsync(request, cancellationToken);

        // Assert
        HttpRequestException exception = await Assert.ThrowsAsync<HttpRequestException>(actAsync);
        Assert.Contains("HTTPS to HTTP", exception.Message, StringComparison.Ordinal);
        Assert.Equal(1, requestCount);
    }

    [Fact]
    public async Task SendAsyncFactoryPipelineAppliesHeadersAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        using HttpResponseMessage okResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("ok", Encoding.UTF8, "text/plain"),
        };
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            req.Headers.TryAddWithoutValidation("X-Client-Token", "factory-header-value");
            return Task.FromResult(okResponse);
        });
#pragma warning restore CA2025

        Mock<IHttpMessageHandlerFactory> factory = CreateHttpMessageHandlerFactory(messageHandler);
        DefaultHttpRequestHandler handler = new(["api.example.test"], factory.Object);

        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);

        // Assert
        Assert.Equal("ok", result.Body);
        Assert.NotNull(messageHandler.LastRequest);
        Assert.Equal("factory-header-value", Assert.Single(messageHandler.LastRequest.Headers.GetValues("X-Client-Token")));
    }

    [Fact]
    public async Task SendAsyncUsesCanonicalRequestUriAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        List<string> requestUrls = [];
        using HttpResponseMessage okResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("ok", Encoding.UTF8, "text/plain"),
        };
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            requestUrls.Add(req.RequestUri!.ToString());
            return Task.FromResult(okResponse);
        });
#pragma warning restore CA2025
        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);

        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = "https://api.example.test/public/../admin/private",
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);

        // Assert
        Assert.Equal("ok", result.Body);
        Assert.Equal(["https://api.example.test/admin/private"], requestUrls);
    }

    [Fact]
    public async Task SendAsyncCreatesFactoryPipelineForRedirectDestinationAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        List<string> requestUrls = [];
        using HttpResponseMessage redirectResponse = new(HttpStatusCode.TemporaryRedirect)
        {
            Headers = { Location = new Uri("https://secondary.example.test/next") },
        };
        using HttpResponseMessage okResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("redirected", Encoding.UTF8, "text/plain"),
        };
#pragma warning disable CA2025
        using TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            requestUrls.Add(req.RequestUri!.ToString());
            return Task.FromResult(requestUrls.Count == 1 ? redirectResponse : okResponse);
        });
#pragma warning restore CA2025

        Mock<IHttpMessageHandlerFactory> factory = CreateHttpMessageHandlerFactory(messageHandler);
        DefaultHttpRequestHandler handler = new(["api.example.test", "secondary.example.test"], factory.Object);

        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);

        // Assert
        Assert.Equal("redirected", result.Body);
        factory.Verify(f => f.CreateHandler(string.Empty), Times.Exactly(2));
        Assert.Equal([TestUrl, "https://secondary.example.test/next"], requestUrls);
    }

    #endregion

    #region Query Parameters and Connection Tests

    [Fact]
    public async Task QueryParametersAreAppendedToUrlAsync()
    {
        // Arrange
        using TestHttpMessageHandler fake = new(static (req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(string.Empty) }));
        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(fake).Object);

        HttpRequestInfo info = new()
        {
            Method = "GET",
            Url = TestUrl,
            QueryParameters = new Dictionary<string, string>
            {
                ["filter"] = "active items",
                ["ids"] = "1,2,3",
            },
        };

        // Act
        await handler.SendAsync(info);

        // Assert
        Assert.NotNull(fake.LastRequest);
        string? query = fake.LastRequest!.RequestUri!.Query;
        Assert.Contains("filter=active%20items", query);
        Assert.Contains("ids=1%2C2%2C3", query);
    }

    [Fact]
    public async Task QueryParametersPreserveExistingQueryStringAsync()
    {
        // Arrange
        using TestHttpMessageHandler fake = new(static (req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(string.Empty) }));
        DefaultHttpRequestHandler handler = new(["api.example.test"], CreateHttpMessageHandlerFactory(fake).Object);

        HttpRequestInfo info = new()
        {
            Method = "GET",
            Url = TestUrl + "?existing=yes",
            QueryParameters = new Dictionary<string, string>
            {
                ["added"] = "true",
            },
        };

        // Act
        await handler.SendAsync(info);

        // Assert
        Assert.Equal("?existing=yes&added=true", fake.LastRequest!.RequestUri!.Query);
    }

    #endregion

    private static DefaultHttpRequestHandler CreateHandlerWithMessageHandler(HttpMessageHandler messageHandler)
    {
        return new(["api.example.test", "secondary.example.test"], CreateHttpMessageHandlerFactory(messageHandler).Object);
    }

    private static Mock<IHttpMessageHandlerFactory> CreateHttpMessageHandlerFactory(HttpMessageHandler messageHandler)
    {
        Mock<IHttpMessageHandlerFactory> factory = new();
        factory.Setup(f => f.CreateHandler(It.IsAny<string>()))
            .Returns(messageHandler);
        return factory;
    }

    private static ServiceProvider CreateServiceProvider()
    {
        ServiceCollection services = new();
        services.AddHttpClient(string.Empty)
            .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
            {
                AllowAutoRedirect = false,
                UseCookies = false,
                CheckCertificateRevocationList = true,
            });
        return services.BuildServiceProvider();
    }

    private sealed class TestHttpMessageHandler : DelegatingHandler
    {
        private readonly Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> _responseFactory;

        public TestHttpMessageHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> responseFactory)
            : base(new HttpClientHandler
            {
                AllowAutoRedirect = false,
                UseCookies = false,
                CheckCertificateRevocationList = true,
            })
        {
            this._responseFactory = responseFactory;
        }

        public HttpRequestMessage? LastRequest { get; private set; }

        public string? LastRequestBody { get; private set; }

        public string? LastRequestContentType { get; private set; }

        public bool IsDisposed { get; private set; }

        public List<string> RequestMethods { get; } = [];

        public List<string?> RequestBodies { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this.LastRequest = request;
            this.RequestMethods.Add(request.Method.Method);
            if (request.Content is not null)
            {
#if NET
                this.LastRequestBody = await request.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
#else
                this.LastRequestBody = await request.Content.ReadAsStringAsync().ConfigureAwait(false);
#endif
                this.RequestBodies.Add(this.LastRequestBody);
                this.LastRequestContentType = request.Content.Headers.ContentType?.MediaType;
            }
            else
            {
                this.RequestBodies.Add(null);
            }
            return await this._responseFactory(request, cancellationToken).ConfigureAwait(false);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                this.IsDisposed = true;
            }

            base.Dispose(disposing);
        }
    }

    private sealed class CookieCaptureServer : IAsyncDisposable
    {
        private const int ExpectedRequestCount = 2;

        private readonly TcpListener _listener;
        private readonly Task<List<string>> _requestsTask;

        public CookieCaptureServer()
        {
            this._listener = new TcpListener(IPAddress.Loopback, 0);
            this._listener.Start();
            int port = ((IPEndPoint)this._listener.LocalEndpoint).Port;
            string baseUrl = $"http://127.0.0.1:{port}";
            this.SetCookieUrl = $"{baseUrl}/set-cookie";
            this.SetCookieRedirectUrl = $"{baseUrl}/set-cookie-redirect";
            this.ReadCookieUrl = $"{baseUrl}/read-cookie";
            this._requestsTask = Task.Run(this.AcceptRequests);
        }

        public string SetCookieUrl { get; }

        public string SetCookieRedirectUrl { get; }

        public string ReadCookieUrl { get; }

        public async Task<IReadOnlyList<string>> ReadRequestsAsync(TimeSpan timeout)
        {
            Task completedTask = await Task.WhenAny(this._requestsTask, Task.Delay(timeout)).ConfigureAwait(false);
            return completedTask == this._requestsTask
                ? await this._requestsTask.ConfigureAwait(false)
                : [];
        }

        public async ValueTask DisposeAsync()
        {
#if NET
            this._listener.Dispose();
#else
            this._listener.Stop();
#endif
            await this._requestsTask.ConfigureAwait(false);
        }

        private List<string> AcceptRequests()
        {
            List<string> requests = [];
            for (int i = 0; i < ExpectedRequestCount; i++)
            {
                try
                {
                    using TcpClient client = this._listener.AcceptTcpClient();
                    client.ReceiveTimeout = 1000;
                    using NetworkStream stream = client.GetStream();
                    string request = ReadRawRequest(stream);
                    requests.Add(request);

                    if (request.StartsWith("GET /set-cookie-redirect ", StringComparison.Ordinal))
                    {
                        WriteRedirectResponse(stream);
                        continue;
                    }

                    string body = request.Contains("Cookie: backend-session=victim-session", StringComparison.OrdinalIgnoreCase)
                        ? "cookie-present"
                        : request.StartsWith("GET /set-cookie ", StringComparison.Ordinal)
                            ? "victim"
                            : "no-cookie";

                    string setCookieHeader = request.StartsWith("GET /set-cookie ", StringComparison.Ordinal)
                        ? "Set-Cookie: backend-session=victim-session; Path=/\r\n"
                        : string.Empty;

                    byte[] responseBytes = Encoding.ASCII.GetBytes(
                        $"HTTP/1.1 200 OK\r\nContent-Length: {body.Length}\r\n{setCookieHeader}Connection: close\r\n\r\n{body}");
                    stream.Write(responseBytes, 0, responseBytes.Length);
                }
                catch (SocketException exception)
                {
                    Trace.WriteLine($"Cookie capture server stopped accepting requests: {exception.Message}");
                    break;
                }
                catch (ObjectDisposedException exception)
                {
                    Trace.WriteLine($"Cookie capture server listener was disposed: {exception.Message}");
                    break;
                }
                catch (IOException exception)
                {
                    Trace.WriteLine($"Cookie capture server stream ended while handling a request: {exception.Message}");
                    break;
                }
            }

            return requests;
        }

        private static void WriteRedirectResponse(NetworkStream stream)
        {
            byte[] responseBytes = Encoding.ASCII.GetBytes(
                "HTTP/1.1 307 Temporary Redirect\r\nLocation: /read-cookie\r\nSet-Cookie: backend-session=victim-session; Path=/\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
            stream.Write(responseBytes, 0, responseBytes.Length);
        }

        private static string ReadRawRequest(NetworkStream stream)
        {
            using MemoryStream rawRequest = new();
            byte[] buffer = new byte[1024];

            while (true)
            {
                int bytesRead = stream.Read(buffer, 0, buffer.Length);
                if (bytesRead == 0)
                {
                    break;
                }

                rawRequest.Write(buffer, 0, bytesRead);
                string currentRequest = Encoding.ASCII.GetString(rawRequest.ToArray());
                if (currentRequest.Contains("\r\n\r\n", StringComparison.Ordinal))
                {
                    return currentRequest;
                }
            }

            return Encoding.ASCII.GetString(rawRequest.ToArray());
        }
    }

    private sealed class RawHttpServer : IAsyncDisposable
    {
        private readonly TcpListener _listener;
        private readonly Task<string?> _rawRequestTask;

        public RawHttpServer()
        {
            this._listener = new TcpListener(IPAddress.Loopback, 0);
            this._listener.Start();
            int port = ((IPEndPoint)this._listener.LocalEndpoint).Port;
            this.Url = $"http://127.0.0.1:{port}/public";
            this._rawRequestTask = Task.Run(this.AcceptAndRespond);
        }

        public string Url { get; }

        public Task<string?> TryReadRequestAsync() =>
            this.TryReadRequestAsync(TimeSpan.FromMilliseconds(500));

        public async Task<string?> TryReadRequestAsync(TimeSpan timeout)
        {
            Task completedTask = await Task.WhenAny(this._rawRequestTask, Task.Delay(timeout)).ConfigureAwait(false);
            return completedTask == this._rawRequestTask
                ? await this._rawRequestTask.ConfigureAwait(false)
                : null;
        }

        public async ValueTask DisposeAsync()
        {
#if NET
            this._listener.Dispose();
#else
            this._listener.Stop();
#endif
            await this._rawRequestTask.ConfigureAwait(false);
        }

        private string? AcceptAndRespond()
        {
            TcpClient client;
            try
            {
                client = this._listener.AcceptTcpClient();
            }
            catch (SocketException)
            {
                return null;
            }
            catch (ObjectDisposedException)
            {
                return null;
            }

            using (client)
            {
                client.ReceiveTimeout = 250;
                using NetworkStream stream = client.GetStream();
                using MemoryStream rawRequest = new();
                byte[] buffer = new byte[1024];

                while (true)
                {
                    int bytesRead;
                    try
                    {
                        bytesRead = stream.Read(buffer, 0, buffer.Length);
                    }
                    catch (IOException)
                    {
                        break;
                    }

                    if (bytesRead == 0)
                    {
                        break;
                    }

                    rawRequest.Write(buffer, 0, bytesRead);
                    string currentRequest = Encoding.ASCII.GetString(rawRequest.ToArray());
                    if (currentRequest.Contains("DELETE /admin", StringComparison.Ordinal))
                    {
                        break;
                    }
                }

                byte[] responseBytes = Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok");
                stream.Write(responseBytes, 0, responseBytes.Length);
                return Encoding.ASCII.GetString(rawRequest.ToArray());
            }
        }
    }

    private sealed class TrackingContent : HttpContent
    {
        private readonly string _content;

        public TrackingContent(string content)
        {
            this._content = content;
        }

        public bool WasRead { get; private set; }

        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context)
        {
            this.WasRead = true;
            byte[] bytes = Encoding.UTF8.GetBytes(this._content);
            return stream.WriteAsync(bytes, 0, bytes.Length);
        }

        protected override bool TryComputeLength(out long length)
        {
            length = Encoding.UTF8.GetByteCount(this._content);
            return true;
        }
    }

    private sealed class StallingContent : HttpContent
    {
        private readonly TaskCompletionSource<object?> _stall = new(TaskCreationOptions.RunContinuationsAsynchronously);

        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) =>
            this._stall.Task;

#if NET
        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context, CancellationToken cancellationToken) =>
            Task.Delay(Timeout.Infinite, cancellationToken);
#endif

        protected override bool TryComputeLength(out long length)
        {
            length = 0;
            return false;
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                this._stall.TrySetCanceled();
            }

            base.Dispose(disposing);
        }
    }
}
