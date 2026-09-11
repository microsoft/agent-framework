// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Reflection;
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
    public async Task SendAsyncTimeoutCancelsResponseBodyReadAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        int requestCount = 0;
        using var response = new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StallingContent(),
        };
        TestHttpMessageHandler messageHandler = new((_, _) =>
        {
            requestCount++;
#pragma warning disable CA2025 // Do not pass 'IDisposable' instances into unawaited tasks
            return Task.FromResult(response);
#pragma warning restore CA2025 // Do not pass 'IDisposable' instances into unawaited tasks
        });

        using HttpClient httpClient = new(messageHandler);
#pragma warning disable CA2025 // Do not pass 'IDisposable' instances into unawaited tasks
        await using DefaultHttpRequestHandler handler = new((_, _) => Task.FromResult<HttpClient?>(httpClient));
#pragma warning restore CA2025 // Do not pass 'IDisposable' instances into unawaited tasks
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
        TestHttpMessageHandler messageHandler = new(async (req, ct) =>
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

        await using DefaultHttpRequestHandler handler = CreateHandlerWithOwnedMessageHandler(messageHandler);
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
        TestHttpMessageHandler messageHandler = new((_, _) =>
        {
            requestCount++;
            return Task.FromResult(requestCount == 1 ? redirectResponse : okResponse);
        });
#pragma warning restore CA2025

        await using DefaultHttpRequestHandler handler = CreateHandlerWithOwnedMessageHandler(messageHandler);
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
        TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            requestCount++;
            return Task.FromResult(requestCount == 1 ? redirectResponse : okResponse);
        });
#pragma warning restore CA2025

        await using DefaultHttpRequestHandler handler = CreateHandlerWithOwnedMessageHandler(messageHandler);
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
        TestHttpMessageHandler messageHandler = new((_, _) =>
        {
            requestCount++;
            return Task.FromResult(redirectResponse);
        });
#pragma warning restore CA2025

        await using DefaultHttpRequestHandler handler = CreateHandlerWithOwnedMessageHandler(messageHandler);
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
        TestHttpMessageHandler messageHandler = new((_, _) =>
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
            await using DefaultHttpRequestHandler handler = CreateHandlerWithOwnedMessageHandler(messageHandler);
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
        TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            requestsWithHeader.Add(req.Headers.Contains("X-Trace-Id"));
            if (requestsWithHeader.Count == 1)
            {
                return Task.FromResult(redirectResponse);
            }

            return Task.FromResult(okResponse);
        });
#pragma warning restore CA2025

        await using DefaultHttpRequestHandler handler = CreateHandlerWithOwnedMessageHandler(messageHandler);
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
        TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            requestUrls.Add(req.RequestUri!.ToString());
            requestsWithHeader.Add(req.Headers.Contains("X-Trace-Id"));
            return Task.FromResult(requestUrls.Count == 1 ? redirectResponse : okResponse);
        });
#pragma warning restore CA2025

        await using DefaultHttpRequestHandler handler = CreateHandlerWithOwnedMessageHandler(messageHandler);

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
        TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            if (req.RequestUri!.AbsolutePath == "/resource")
            {
                return Task.FromResult(redirectResponse);
            }

            return Task.FromResult(okResponse);
        });
#pragma warning restore CA2025

        await using DefaultHttpRequestHandler handler = CreateHandlerWithOwnedMessageHandler(messageHandler);
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
        TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            requestCount++;
            return Task.FromResult(redirectResponse);
        });
#pragma warning restore CA2025

        await using DefaultHttpRequestHandler handler = CreateHandlerWithOwnedMessageHandler(messageHandler);
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
    public async Task SendAsyncProviderClientAllowsScopedDefaultHeadersOnInitialRequestAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        using HttpResponseMessage okResponse = new(HttpStatusCode.OK)
        {
            Content = new StringContent("ok", Encoding.UTF8, "text/plain"),
        };
#pragma warning disable CA2025
        TestHttpMessageHandler messageHandler = new((req, _) =>
            Task.FromResult(okResponse));
#pragma warning restore CA2025
        using HttpClient providerClient = new(messageHandler);
        providerClient.DefaultRequestHeaders.TryAddWithoutValidation("X-Client-Token", "provider-header-value");

        int providerCallCount = 0;
#pragma warning disable CA2025
        await using DefaultHttpRequestHandler handler = new((_, _) =>
        {
            providerCallCount++;
            return Task.FromResult<HttpClient?>(providerClient);
        });
#pragma warning restore CA2025

        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);

        // Assert
        Assert.Equal("ok", result.Body);
        Assert.Equal(1, providerCallCount);
    }

    [Fact]
    public async Task SendAsyncSuppliedClientReturnsRedirectResponseAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        using HttpResponseMessage redirectResponse = new(HttpStatusCode.TemporaryRedirect)
        {
            Headers = { Location = new Uri("https://secondary.example.test/next") },
        };
#pragma warning disable CA2025
        TestHttpMessageHandler primaryMessageHandler = new((req, _) =>
            Task.FromResult(redirectResponse));
#pragma warning restore CA2025
        using HttpClient primaryClient = new(primaryMessageHandler);
        primaryClient.DefaultRequestHeaders.TryAddWithoutValidation("Ocp-Apim-Subscription-Key", "provider-header-value");

        int providerCallCount = 0;
#pragma warning disable CA2025
        await using DefaultHttpRequestHandler handler = new((_, _) =>
        {
            providerCallCount++;
            return Task.FromResult<HttpClient?>(primaryClient);
        });
#pragma warning restore CA2025

        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);

        // Assert
        Assert.Equal(307, result.StatusCode);
        Assert.False(result.IsSuccessStatusCode);
        Assert.NotNull(result.Headers);
        Assert.Equal("https://secondary.example.test/next", Assert.Single(result.Headers!["Location"]));
        Assert.Equal(1, providerCallCount);
    }

    [Fact]
    public async Task SendAsyncInvokesProviderForRedirectDestinationAsync()
    {
        // Arrange
        CancellationToken cancellationToken = TestContext.Current.CancellationToken;
        List<string> providerUrls = [];
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
        TestHttpMessageHandler messageHandler = new((req, _) =>
        {
            requestUrls.Add(req.RequestUri!.ToString());
            return Task.FromResult(requestUrls.Count == 1 ? redirectResponse : okResponse);
        });
#pragma warning restore CA2025

        await using DefaultHttpRequestHandler handler = CreateHandlerWithOwnedMessageHandler(messageHandler, (info, _) =>
        {
            providerUrls.Add(info.Url);
            return Task.FromResult<HttpClient?>(null);
        });

        HttpRequestInfo request = new()
        {
            Method = "GET",
            Url = TestUrl,
        };

        // Act
        HttpRequestResult result = await handler.SendAsync(request, cancellationToken);

        // Assert
        Assert.Equal("redirected", result.Body);
        Assert.Equal(2, providerUrls.Count);
        Assert.Equal(TestUrl, providerUrls[0]);
        Assert.Equal("https://secondary.example.test/next", providerUrls[1]);
        Assert.Equal(providerUrls, requestUrls);
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

    private static DefaultHttpRequestHandler CreateHandlerWithOwnedMessageHandler(
        HttpMessageHandler ownedHttpMessageHandler,
        Func<HttpRequestInfo, CancellationToken, Task<HttpClient?>>? httpClientProvider = null)
    {
        DefaultHttpRequestHandler handler = new(httpClientProvider);
        FieldInfo? ownedHttpClientField = typeof(DefaultHttpRequestHandler).GetField("_ownedHttpClient", BindingFlags.Instance | BindingFlags.NonPublic);
        Assert.NotNull(ownedHttpClientField);
        ownedHttpClientField.SetValue(handler, new Lazy<HttpClient>(() => new HttpClient(ownedHttpMessageHandler), LazyThreadSafetyMode.ExecutionAndPublication));
        return handler;
    }

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
