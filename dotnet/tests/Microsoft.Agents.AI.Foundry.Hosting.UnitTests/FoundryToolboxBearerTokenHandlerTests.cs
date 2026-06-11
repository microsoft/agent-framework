// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

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
    public async Task SendAsync_UsesAiAzureComScopeAsync()
    {
        // Arrange
        var capturedContexts = new List<TokenRequestContext>();
        var credential = new Mock<TokenCredential>();
        credential
            .Setup(c => c.GetTokenAsync(It.IsAny<TokenRequestContext>(), It.IsAny<CancellationToken>()))
            .Callback<TokenRequestContext, CancellationToken>((ctx, _) => capturedContexts.Add(ctx))
            .ReturnsAsync(new AccessToken(FakeToken, DateTimeOffset.MaxValue));
        var (handler, _) = CreateHandlerPair(credential);
        using var invoker = new HttpMessageInvoker(handler);

        // Act
        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        await invoker.SendAsync(request, CancellationToken.None);

        // Assert: spec §4 mandates the https://ai.azure.com audience.
        Assert.Single(capturedContexts);
        Assert.Contains("https://ai.azure.com/.default", capturedContexts[0].Scopes);
    }

    [Fact]
    public async Task SendAsync_AlwaysInjectsMandatoryFoundryFeaturesHeaderAsync()
    {
        // Arrange
        var (handler, _) = CreateHandlerPair(featuresHeader: null);
        using var invoker = new HttpMessageInvoker(handler);

        // Act
        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        using var response = await invoker.SendAsync(request, CancellationToken.None);

        // Assert: spec §2 requires Foundry-Features: Toolboxes=V1Preview on every request.
        Assert.True(request.Headers.TryGetValues("Foundry-Features", out var values));
        Assert.Equal("Toolboxes=V1Preview", values.Single());
    }

    [Fact]
    public async Task SendAsync_MergesMandatoryAndOverrideFeaturesAsync()
    {
        var (handler, _) = CreateHandlerPair(featuresHeader: "feature1,feature2");
        using var invoker = new HttpMessageInvoker(handler);

        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        await invoker.SendAsync(request, CancellationToken.None);

        Assert.True(request.Headers.TryGetValues("Foundry-Features", out var values));
        var header = values.Single();
        Assert.Contains("Toolboxes=V1Preview", header, StringComparison.Ordinal);
        Assert.Contains("feature1", header, StringComparison.Ordinal);
        Assert.Contains("feature2", header, StringComparison.Ordinal);
    }

    [Fact]
    public async Task SendAsync_DoesNotDuplicateMandatoryFlagAsync()
    {
        // Override already contains the mandatory flag — must not be duplicated in the merged value.
        var (handler, _) = CreateHandlerPair(featuresHeader: "Toolboxes=V1Preview");
        using var invoker = new HttpMessageInvoker(handler);

        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        await invoker.SendAsync(request, CancellationToken.None);

        Assert.True(request.Headers.TryGetValues("Foundry-Features", out var values));
        var header = values.Single();
        var count = 0;
        var idx = 0;
        while ((idx = header.IndexOf("Toolboxes=V1Preview", idx, StringComparison.OrdinalIgnoreCase)) >= 0)
        {
            count++;
            idx += "Toolboxes=V1Preview".Length;
        }
        Assert.Equal(1, count);
    }

    [Fact]
    public async Task SendAsync_PropagatesTraceContextFromActivityAsync()
    {
        // Arrange: activate an Activity so Activity.Current is populated.
        using var listener = new ActivityListener
        {
            ShouldListenTo = _ => true,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllData,
        };
        ActivitySource.AddActivityListener(listener);
        using var source = new ActivitySource("test-source");
        using var activity = source.StartActivity("test-op")!;
        Assert.NotNull(activity);
        activity.TraceStateString = "vendor=value";
        activity.AddBaggage("user", "alice");

        var (handler, _) = CreateHandlerPair();
        using var invoker = new HttpMessageInvoker(handler);

        // Act
        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        await invoker.SendAsync(request, CancellationToken.None);

        // Assert: spec §6.3 requires traceparent/tracestate/baggage propagation.
        Assert.True(request.Headers.TryGetValues("traceparent", out var tpValues));
        Assert.Contains(activity.TraceId.ToString(), tpValues.Single(), StringComparison.Ordinal);

        Assert.True(request.Headers.TryGetValues("tracestate", out var tsValues));
        Assert.Equal("vendor=value", tsValues.Single());

        Assert.True(request.Headers.TryGetValues("baggage", out var bgValues));
        Assert.Contains("user=alice", bgValues.Single(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task SendAsync_DoesNotOverrideExistingTraceparentAsync()
    {
        // Caller pre-set traceparent on the message; must not be duplicated or replaced.
        using var listener = new ActivityListener
        {
            ShouldListenTo = _ => true,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllData,
        };
        ActivitySource.AddActivityListener(listener);
        using var source = new ActivitySource("test-source");
        using var activity = source.StartActivity("test-op")!;
        Assert.NotNull(activity);

        var (handler, _) = CreateHandlerPair();
        using var invoker = new HttpMessageInvoker(handler);

        const string PresetTraceparent = "00-00000000000000000000000000000001-0000000000000001-01";
        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        request.Headers.TryAddWithoutValidation("traceparent", PresetTraceparent);

        // Act
        await invoker.SendAsync(request, CancellationToken.None);

        // Assert
        Assert.True(request.Headers.TryGetValues("traceparent", out var values));
        var list = values.ToList();
        Assert.Single(list);
        Assert.Equal(PresetTraceparent, list[0]);
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
