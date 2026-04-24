// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;

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
        handler.Should().NotBeNull();
    }

    [Fact]
    public async Task ConstructorWithNullProviderCreatesInstanceAsync()
    {
        // Act
        await using DefaultHttpRequestHandler handler = new(httpClientProvider: null);

        // Assert
        handler.Should().NotBeNull();
    }

    [Fact]
    public void ConstructorWithNullHttpClientThrows()
    {
        // Act
        Action act = () => _ = new DefaultHttpRequestHandler((HttpClient)null!);

        // Assert
        act.Should().Throw<ArgumentNullException>();
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
        messageHandler.LastRequest.Should().NotBeNull();
        messageHandler.LastRequest!.RequestUri!.ToString().Should().Be(TestUrl);
        result.Body.Should().Be("ok");
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
        Func<Task> act = async () => await suppliedClient.GetAsync(new Uri(TestUrl));
        await act.Should().NotThrowAsync<ObjectDisposedException>();
    }

    #endregion

    #region Argument Validation Tests

    [Fact]
    public async Task SendAsyncWithNullRequestThrowsAsync()
    {
        // Arrange
        await using DefaultHttpRequestHandler handler = new();

        // Act
        Func<Task> act = async () => await handler.SendAsync(null!);

        // Assert
        await act.Should().ThrowAsync<ArgumentNullException>();
    }

    [Fact]
    public async Task SendAsyncWithEmptyUrlThrowsAsync()
    {
        // Arrange
        await using DefaultHttpRequestHandler handler = new();
        HttpRequestInfo request = new() { Method = "GET", Url = "" };

        // Act
        Func<Task> act = async () => await handler.SendAsync(request);

        // Assert
        await act.Should().ThrowAsync<ArgumentException>();
    }

    [Fact]
    public async Task SendAsyncWithEmptyMethodThrowsAsync()
    {
        // Arrange
        await using DefaultHttpRequestHandler handler = new();
        HttpRequestInfo request = new() { Method = "", Url = TestUrl };

        // Act
        Func<Task> act = async () => await handler.SendAsync(request);

        // Assert
        await act.Should().ThrowAsync<ArgumentException>();
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
        messageHandler.LastRequest.Should().NotBeNull();
        messageHandler.LastRequest!.Method.Should().Be(HttpMethod.Get);
        messageHandler.LastRequest.RequestUri!.ToString().Should().Be(TestUrl);
        result.StatusCode.Should().Be(200);
        result.IsSuccessStatusCode.Should().BeTrue();
        result.Body.Should().Be("hello");
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
            messageHandler.LastRequest!.Method.Method.Should().Be(method);
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
        messageHandler.LastRequest!.Method.Method.Should().Be("CUSTOM");
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
        messageHandler.LastRequestBody.Should().Be("{\"hello\":\"world\"}");
        messageHandler.LastRequestContentType.Should().Be("application/json");
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
        messageHandler.LastRequest!.Headers.Authorization!.ToString().Should().Be("Bearer secret");
        messageHandler.LastRequest.Headers.Accept.Should().Contain(mediaType => mediaType.MediaType == "application/json");
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
        messageHandler.LastRequest!.Content!.Headers.ContentLanguage.Should().Contain("en-US");
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
        result.Headers.Should().NotBeNull();
        result.Headers!.Should().ContainKey("X-Request-Id");
        result.Headers!["Set-Cookie"].Should().BeEquivalentTo(s_setCookieValues);
        // Content headers also flattened in.
        result.Headers!.Should().ContainKey("Content-Type");
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
        result.IsSuccessStatusCode.Should().BeFalse();
        result.StatusCode.Should().Be(400);
        result.Body.Should().Be("bad request");
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
        Func<Task> act = async () => await handler.SendAsync(request);

        // Assert
        await act.Should().ThrowAsync<OperationCanceledException>();
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
        Func<Task> act = async () => await handler.SendAsync(request);

        // Assert
        await act.Should().ThrowAsync<Exception>();
        providerCallCount.Should().Be(1);
    }

    #endregion

    #region DisposeAsync

    [Fact]
    public async Task DisposeAsyncCompletesAsync()
    {
        // Arrange
        DefaultHttpRequestHandler handler = new();

        // Act
        Func<Task> act = async () => await handler.DisposeAsync();

        // Assert
        await act.Should().NotThrowAsync();
    }

    [Fact]
    public async Task DisposeAsyncCalledMultipleTimesSucceedsAsync()
    {
        // Arrange
        DefaultHttpRequestHandler handler = new();

        // Act
        await handler.DisposeAsync();
        Func<Task> second = async () => await handler.DisposeAsync();

        // Assert
        await second.Should().NotThrowAsync();
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
        fake.LastRequest.Should().NotBeNull();
        string? query = fake.LastRequest!.RequestUri!.Query;
        query.Should().Contain("filter=active%20items");
        query.Should().Contain("ids=1%2C2%2C3");
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
        fake.LastRequest!.RequestUri!.Query.Should().Be("?existing=yes&added=true");
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
