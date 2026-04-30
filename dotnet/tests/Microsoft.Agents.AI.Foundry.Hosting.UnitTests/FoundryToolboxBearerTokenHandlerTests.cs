// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Agents.AI.Foundry.Hosting;
using Moq;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

public class FoundryToolboxBearerTokenHandlerTests
{
    private const string FakeToken = "test-bearer-token";

    private static Mock<TokenCredential> CreateMockCredential()
    {
        var mock = new Mock<TokenCredential>();
        mock.Setup(c => c.GetTokenAsync(It.IsAny<TokenRequestContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AccessToken(FakeToken, DateTimeOffset.UtcNow.AddHours(1)));
        return mock;
    }

    private static (FoundryToolboxBearerTokenHandler Handler, CountingHandler Inner) CreateHandlerPair(
        Mock<TokenCredential>? credential = null,
        string? featuresHeader = null,
        HttpStatusCode statusCode = HttpStatusCode.OK)
    {
        credential ??= CreateMockCredential();
        var inner = new CountingHandler(statusCode);
        var handler = new FoundryToolboxBearerTokenHandler(credential.Object, featuresHeader)
        {
            InnerHandler = inner
        };
        return (handler, inner);
    }

    [Fact]
    public async Task SendAsync_InjectsBearerTokenAsync()
    {
        var (handler, _) = CreateHandlerPair();
        using var invoker = new HttpMessageInvoker(handler);

        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        using var response = await invoker.SendAsync(request, CancellationToken.None);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("Bearer", request.Headers.Authorization?.Scheme);
        Assert.Equal(FakeToken, request.Headers.Authorization?.Parameter);
    }

    [Fact]
    public async Task SendAsync_InjectsFoundryFeaturesHeaderAsync()
    {
        var (handler, _) = CreateHandlerPair(featuresHeader: "feature1,feature2");
        using var invoker = new HttpMessageInvoker(handler);

        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        using var response = await invoker.SendAsync(request, CancellationToken.None);

        Assert.True(request.Headers.TryGetValues("Foundry-Features", out var values));
        Assert.Contains("feature1,feature2", values);
    }

    [Fact]
    public async Task SendAsync_OmitsFeaturesHeaderWhenNullAsync()
    {
        var (handler, _) = CreateHandlerPair(featuresHeader: null);
        using var invoker = new HttpMessageInvoker(handler);

        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        using var response = await invoker.SendAsync(request, CancellationToken.None);

        Assert.False(request.Headers.Contains("Foundry-Features"));
    }

    [Theory]
    [InlineData(HttpStatusCode.OK)]
    [InlineData(HttpStatusCode.Created)]
    [InlineData(HttpStatusCode.BadRequest)]
    [InlineData(HttpStatusCode.NotFound)]
    public async Task SendAsync_NonRetryableStatusCode_ReturnsImmediatelyAsync(HttpStatusCode statusCode)
    {
        var (handler, inner) = CreateHandlerPair(statusCode: statusCode);
        using var invoker = new HttpMessageInvoker(handler);

        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        using var response = await invoker.SendAsync(request, CancellationToken.None);

        Assert.Equal(statusCode, response.StatusCode);
        Assert.Equal(1, inner.CallCount);
    }

    [Theory]
    [InlineData(HttpStatusCode.TooManyRequests)]
    [InlineData(HttpStatusCode.InternalServerError)]
    [InlineData(HttpStatusCode.BadGateway)]
    [InlineData(HttpStatusCode.ServiceUnavailable)]
    public async Task SendAsync_RetryableStatusCode_RetriesMaxTimesAsync(HttpStatusCode statusCode)
    {
        var (handler, inner) = CreateHandlerPair(statusCode: statusCode);
        using var invoker = new HttpMessageInvoker(handler);

        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        using var response = await invoker.SendAsync(request, CancellationToken.None);

        // MaxRetries is 3, so exactly 3 total attempts (not 4).
        Assert.Equal(3, inner.CallCount);
        Assert.Equal(statusCode, response.StatusCode);
    }

    [Fact]
    public async Task SendAsync_RetryableStatusCode_SucceedsOnSecondAttemptAsync()
    {
        // First call returns 503, second returns 200.
        var inner = new SequenceHandler(
            HttpStatusCode.ServiceUnavailable,
            HttpStatusCode.OK);

        var handler = new FoundryToolboxBearerTokenHandler(CreateMockCredential().Object, null)
        {
            InnerHandler = inner
        };
        using var invoker = new HttpMessageInvoker(handler);

        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        using var response = await invoker.SendAsync(request, CancellationToken.None);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(2, inner.CallCount);
    }

    /// <summary>
    /// A test handler that always returns the configured status code and counts how many times it was called.
    /// </summary>
    private sealed class CountingHandler : HttpMessageHandler
    {
        private readonly HttpStatusCode _statusCode;
        private int _callCount;

        public int CallCount => this._callCount;

        public CountingHandler(HttpStatusCode statusCode)
        {
            this._statusCode = statusCode;
        }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            Interlocked.Increment(ref this._callCount);
            return Task.FromResult(new HttpResponseMessage(this._statusCode));
        }
    }

    /// <summary>
    /// A test handler that returns status codes from a sequence, cycling through them.
    /// </summary>
    private sealed class SequenceHandler : HttpMessageHandler
    {
        private readonly HttpStatusCode[] _statusCodes;
        private int _callCount;

        public int CallCount => this._callCount;

        public SequenceHandler(params HttpStatusCode[] statusCodes)
        {
            this._statusCodes = statusCodes;
        }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            var index = Interlocked.Increment(ref this._callCount) - 1;
            var statusCode = index < this._statusCodes.Length
                ? this._statusCodes[index]
                : this._statusCodes[^1];
            return Task.FromResult(new HttpResponseMessage(statusCode));
        }
    }
}
