// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

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
    public async Task ConstructorWithNoParametersCreatesInstanceAsync()
    {
        // Act
        await using DefaultHttpRequestHandler handler = new();

        // Assert
        Assert.NotNull(handler);
    }

    [Fact]
    public async Task ConstructorWithNullProviderCreatesInstanceAsync()
    {
        // Act
        await using DefaultHttpRequestHandler handler = new(httpClientProvider: null);

        // Assert
        Assert.NotNull(handler);
    }

    [Fact]
    public void ConstructorWithNullHttpClientThrows()
    {
        // Act
        static void act() => _ = new DefaultHttpRequestHandler((HttpClient)null!);

        // Assert
        Assert.Throws<ArgumentNullException>(act);
    }

    [Fact]
    public async Task ConstructorWithHttpClientUsesSuppliedClientForAllRequestsAsync()
    {
        // Arrange
        TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("ok", Encoding.UTF8, "text/plain"),
            }));
        using HttpClient suppliedClient = new(messageHandler);
        await using DefaultHttpRequestHandler handler = new(suppliedClient);
        HttpRequestInfo request = new() { Method = "GET", Url = TestUrl };

        // Act
        HttpRequestResult result = await handler.SendAsync(request);

        // Assert - the supplied HttpClient's underlying handler saw the request
        Assert.NotNull(messageHandler.LastRequest);
        Assert.Equal(TestUrl, messageHandler.LastRequest!.RequestUri!.ToString());
        Assert.Equal("ok", result.Body);
    }

    [Fact]
    public async Task DisposeAsyncDoesNotDisposeCallerSuppliedHttpClientAsync()
    {
        // Arrange
        TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)));
        using HttpClient suppliedClient = new(messageHandler);

        // Act
        DefaultHttpRequestHandler handler = new(suppliedClient);
        await handler.DisposeAsync();

        // Assert - supplied client remains usable (not disposed)
        async Task actAsync() => await suppliedClient.GetAsync(new Uri(TestUrl));
        Assert.IsNotType<ObjectDisposedException>(await Record.ExceptionAsync(actAsync));
    }

    #endregion

    #region Argument Validation Tests

    [Fact]
    public async Task SendAsyncWithNullRequestThrowsAsync()
    {
        // Arrange
        await using DefaultHttpRequestHandler handler = new();

        // Act
        async Task actAsync() => await handler.SendAsync(null!);

        // Assert
        await Assert.ThrowsAsync<ArgumentNullException>(actAsync);
    }

    [Fact]
    public async Task SendAsyncWithEmptyUrlThrowsAsync()
    {
        // Arrange
        await using DefaultHttpRequestHandler handler = new();
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
        await using DefaultHttpRequestHandler handler = new();
        HttpRequestInfo request = new() { Method = "", Url = TestUrl };

        // Act
        async Task actAsync() => await handler.SendAsync(request);

        // Assert
        await Assert.ThrowsAsync<ArgumentException>(actAsync);
    }

    #endregion

    #region Send Behavior Tests

    [Fact]
    public async Task SendAsyncUsesProvidedHttpClientAsync()
    {
        // Arrange
        TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("hello", Encoding.UTF8, "text/plain"),
            }));

        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(new HttpClient(messageHandler)));

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
        TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)));

        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(new HttpClient(messageHandler)));

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
        TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)));
        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(new HttpClient(messageHandler)));
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
        TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)));

        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(new HttpClient(messageHandler)));

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
        TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)));

        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(new HttpClient(messageHandler)));

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
    public async Task SendAsyncRoutesContentHeadersToBodyAsync()
    {
        // Arrange
        TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)));

        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(new HttpClient(messageHandler)));

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
        TestHttpMessageHandler messageHandler = new((req, _) =>
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

        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(new HttpClient(messageHandler)));

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
    public async Task SendAsyncReturnsFailureStatusWithoutThrowingAsync()
    {
        // Arrange
        TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.BadRequest)
            {
                Content = new StringContent("bad request", Encoding.UTF8, "text/plain"),
            }));

        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(new HttpClient(messageHandler)));

        HttpRequestInfo request = new() { Method = "GET", Url = TestUrl };

        // Act
        HttpRequestResult result = await handler.SendAsync(request);

        // Assert
        Assert.False(result.IsSuccessStatusCode);
        Assert.Equal(400, result.StatusCode);
        Assert.Equal("bad request", result.Body);
    }

    [Fact]
    public async Task SendAsyncTimeoutCancelsRequestAsync()
    {
        // Arrange
        TestHttpMessageHandler messageHandler = new(async (req, ct) =>
        {
            await Task.Delay(TimeSpan.FromSeconds(5), ct).ConfigureAwait(false);
            return new HttpResponseMessage(HttpStatusCode.OK);
        });

        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(new HttpClient(messageHandler)));

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
    public async Task SendAsyncFallsBackToOwnedClientWhenProviderReturnsNullAsync()
    {
        // Arrange
        int providerCallCount = 0;
        await using DefaultHttpRequestHandler handler = new((_, _) =>
        {
            providerCallCount++;
            return Task.FromResult<HttpClient?>(null);
        });

        HttpRequestInfo request = new() { Method = "GET", Url = "http://127.0.0.1:1/" };

        // Act - owned client will attempt real network and fail, but provider path should have been consulted first.
        async Task actAsync() => await handler.SendAsync(request);

        // Assert
        await Assert.ThrowsAnyAsync<Exception>(actAsync);
        Assert.Equal(1, providerCallCount);
    }

    #endregion

    #region DisposeAsync

    [Fact]
    public async Task DisposeAsyncCompletesAsync()
    {
        // Arrange
        DefaultHttpRequestHandler handler = new();

        // Act
        async Task actAsync() => await handler.DisposeAsync();

        // Assert
        Assert.Null(await Record.ExceptionAsync(actAsync));
    }

    [Fact]
    public async Task DisposeAsyncCalledMultipleTimesSucceedsAsync()
    {
        // Arrange
        DefaultHttpRequestHandler handler = new();

        // Act
        await handler.DisposeAsync();
        async Task secondAsync() => await handler.DisposeAsync();

        // Assert
        Assert.Null(await Record.ExceptionAsync(secondAsync));
    }

    #endregion

    #region Query Parameters and Connection Tests

    [Fact]
    public async Task QueryParametersAreAppendedToUrlAsync()
    {
        // Arrange
        TestHttpMessageHandler fake = new(static (req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(string.Empty) }));
        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(new HttpClient(fake)));

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
        TestHttpMessageHandler fake = new(static (req, _) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(string.Empty) }));
        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(new HttpClient(fake)));

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

    private sealed class TestHttpMessageHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> _responseFactory;

        public TestHttpMessageHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> responseFactory)
        {
            this._responseFactory = responseFactory;
        }

        public HttpRequestMessage? LastRequest { get; private set; }

        public string? LastRequestBody { get; private set; }

        public string? LastRequestContentType { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this.LastRequest = request;
            if (request.Content is not null)
            {
#if NET
                this.LastRequestBody = await request.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
#else
                this.LastRequestBody = await request.Content.ReadAsStringAsync().ConfigureAwait(false);
#endif
                this.LastRequestContentType = request.Content.Headers.ContentType?.MediaType;
            }
            return await this._responseFactory(request, cancellationToken).ConfigureAwait(false);
        }
    }
}
