// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using ModelContextProtocol.Client;
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
        var handler = new FoundryToolboxBearerTokenHandler(
            credential.Object,
            featuresHeader,
            new Uri("https://example.com"))
        {
            InnerHandler = inner
        };
        return (handler, inner);
    }

    [Fact]
    public async Task SendAsync_ForwardsCallIdWhenSetAsync()
    {
        // Arrange
        var (handler, _) = CreateHandlerPair();
        using var invoker = new HttpMessageInvoker(handler);
        HostedCallContext.CallId = "call-abc";

        try
        {
            // Act
            using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
            using var response = await invoker.SendAsync(request, CancellationToken.None);

            // Assert
            Assert.True(request.Headers.TryGetValues("x-agent-foundry-call-id", out var values));
            Assert.Equal("call-abc", values!.Single());
        }
        finally
        {
            HostedCallContext.CallId = null;
        }
    }

    [Fact]
    public async Task SendAsync_OmitsCallIdWhenAbsentAsync()
    {
        // Arrange
        var (handler, _) = CreateHandlerPair();
        using var invoker = new HttpMessageInvoker(handler);
        HostedCallContext.CallId = null;

        // Act
        using var request = new HttpRequestMessage(HttpMethod.Get, "https://example.com/api");
        using var response = await invoker.SendAsync(request, CancellationToken.None);

        // Assert
        Assert.False(request.Headers.Contains("x-agent-foundry-call-id"));
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
    public async Task SendAsync_CrossOriginRequest_DoesNotInjectFoundryHeadersAsync()
    {
        // Arrange: the handler is created for a trusted toolbox origin and first sends a
        // legitimate request there before the transport attempts a different origin.
        var credential = CreateMockCredential();
        var handler = new FoundryToolboxBearerTokenHandler(
            credential.Object,
            null,
            new Uri("https://trusted.example.com"))
        {
            InnerHandler = new CountingHandler(HttpStatusCode.OK)
        };
        using var invoker = new HttpMessageInvoker(handler);
        HostedCallContext.CallId = "call-abc";

        try
        {
            using var trustedRequest = new HttpRequestMessage(HttpMethod.Post, "https://trusted.example.com/mcp");
            using var trustedResponse = await invoker.SendAsync(trustedRequest, CancellationToken.None);
            Assert.Equal(FakeToken, trustedRequest.Headers.Authorization?.Parameter);
            Assert.True(trustedRequest.Headers.Contains("x-agent-foundry-call-id"));

            // Act: legacy MCP SSE can construct a new request from a server-advertised
            // absolute endpoint, so model that foreign-origin request directly.
            using var crossOriginRequest = new HttpRequestMessage(HttpMethod.Post, "https://untrusted.example/collect");
            using var crossOriginResponse = await invoker.SendAsync(crossOriginRequest, CancellationToken.None);

            // Assert: Foundry credentials, internal feature negotiation, and platform call
            // context must remain on the configured toolbox origin.
            Assert.Null(crossOriginRequest.Headers.Authorization);
            Assert.False(crossOriginRequest.Headers.Contains("Foundry-Features"));
            Assert.False(crossOriginRequest.Headers.Contains("x-agent-foundry-call-id"));
            credential.Verify(
                value => value.GetTokenAsync(It.IsAny<TokenRequestContext>(), It.IsAny<CancellationToken>()),
                Times.Once);
        }
        finally
        {
            HostedCallContext.CallId = null;
        }
    }

    [Theory]
    [InlineData("https://trusted.example.com/toolboxes/test/mcp", "https://trusted.example.com/other", true)]
    [InlineData("https://trusted.example.com/toolboxes/test/mcp", "https://TRUSTED.Example.COM/mcp", true)]
    [InlineData("https://trusted.example.com/toolboxes/test/mcp", "https://trusted.example.com:443/mcp", true)]
    [InlineData("https://trusted.example.com:443/toolboxes/test/mcp", "https://trusted.example.com/mcp", true)]
    [InlineData("https://trusted.example.com/toolboxes/test/mcp", "http://trusted.example.com/mcp", false)]
    [InlineData("https://trusted.example.com/toolboxes/test/mcp", "https://trusted.example.com:8443/mcp", false)]
    [InlineData("https://trusted.example.com/toolboxes/test/mcp", "https://untrusted.example/mcp", false)]
    public async Task CreateToolboxHttpMessageHandler_AttachesCredentialsOnlyForSameOriginAsync(
        string pinnedEndpoint,
        string requestUri,
        bool expectedSameOrigin)
    {
        // Arrange: origin equality covers scheme, host, and port. Host casing and an explicit
        // default port are the same origin; a different scheme, port, or host is not.
        var capture = new HeaderCaptureHandler();
        using var handler = FoundryToolboxService.CreateToolboxHttpMessageHandler(
            new Uri(pinnedEndpoint),
            CreateMockCredential().Object,
            featuresHeader: null,
            capture);
        using var invoker = new HttpMessageInvoker(handler);
        using var request = new HttpRequestMessage(HttpMethod.Post, requestUri);

        // Act
        using var response = await invoker.SendAsync(request, CancellationToken.None);

        // Assert: a same-origin request keeps valid authentication, and any other origin
        // receives no Foundry credentials.
        Assert.Equal(
            expectedSameOrigin,
            FoundryToolboxOriginPinningHandler.IsSameOrigin(new Uri(requestUri), new Uri(pinnedEndpoint)));
        Assert.Equal(expectedSameOrigin, capture.SawAuthorization);
        Assert.Equal(expectedSameOrigin, capture.SawFoundryFeatures);
    }

    [Fact]
    public async Task ToolboxTransport_ServerSelectedCrossOriginEndpoint_DoesNotReceiveBearerTokenAsync()
    {
        // Arrange: use OpenToolboxAsync's production factories with a harmless in-memory MCP
        // peer that would force AutoDetect to legacy SSE and advertise an absolute foreign
        // endpoint if transport negotiation were ever loosened.
        var trustedEndpoint = new Uri("https://trusted.example.com/toolboxes/test/mcp");
        var foreignEndpoint = new Uri("https://untrusted.example/collect");
        var scriptedHandler = new CrossOriginSseHandler(trustedEndpoint, foreignEndpoint);
        var credential = CreateMockCredential();
        var messageHandler = FoundryToolboxService.CreateToolboxHttpMessageHandler(
            trustedEndpoint,
            credential.Object,
            featuresHeader: null,
            scriptedHandler);
        using var httpClient = new HttpClient(messageHandler);
        var transportOptions = FoundryToolboxService.CreateToolboxTransportOptions(trustedEndpoint, "test");
        await using var transport = new HttpClientTransport(transportOptions, httpClient);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));

        // Act: the trusted endpoint rejects the Streamable HTTP probe. Client creation must
        // fail there instead of negotiating down to the scripted SSE endpoint.
        await Assert.ThrowsAnyAsync<Exception>(
            async () => await McpClient.CreateAsync(transport, cancellationToken: timeout.Token));

        // Assert: Streamable HTTP performs only the configured-origin probe. It cannot
        // negotiate down to legacy SSE or adopt the server-selected foreign endpoint.
        Assert.True(scriptedHandler.SawStreamableHttpProbe);
        Assert.False(scriptedHandler.SawLegacySseFallback);
        Assert.False(scriptedHandler.SawForeignEndpointRequest);
        Assert.Null(scriptedHandler.ForeignAuthorization);
        credential.Verify(
            value => value.GetTokenAsync(It.IsAny<TokenRequestContext>(), It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public void CreateToolboxTransportOptions_UsesStreamableHttp()
    {
        // Arrange
        var endpoint = new Uri("https://trusted.example.com/toolboxes/test/mcp");

        // Act
        var options = FoundryToolboxService.CreateToolboxTransportOptions(endpoint, "test");

        // Assert
        Assert.Equal(HttpTransportMode.StreamableHttp, options.TransportMode);
        Assert.Equal(endpoint, options.Endpoint);
    }

    [Fact]
    public void CreateToolboxPrimaryHttpMessageHandler_DisablesAmbientCredentialFlow()
    {
        // Act
        using var handler = FoundryToolboxService.CreateToolboxPrimaryHttpMessageHandler();

        // Assert
        Assert.False(handler.UseCookies);
        Assert.False(handler.AllowAutoRedirect);
        Assert.True(handler.CheckCertificateRevocationList);
    }

    [Fact]
    public async Task CreateToolboxHttpMessageHandler_CrossOriginRequestStripsCredentialHeadersAsync()
    {
        // Arrange: the production pipeline places the bearer handler outside origin
        // pinning so credentials are removed before the primary handler sees the request.
        var capture = new HeaderCaptureHandler();
        var credential = CreateMockCredential();
        using var handler = FoundryToolboxService.CreateToolboxHttpMessageHandler(
            new Uri("https://trusted.example.com/toolboxes/test/mcp"),
            credential.Object,
            featuresHeader: null,
            capture);
        using var invoker = new HttpMessageInvoker(handler);
        using var request = new HttpRequestMessage(HttpMethod.Post, "https://untrusted.example/collect");
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer preexisting");
        request.Headers.TryAddWithoutValidation("Proxy-Authorization", "Basic preexisting");
        request.Headers.TryAddWithoutValidation("Cookie", "session=preexisting");

        // Act
        using var response = await invoker.SendAsync(request, CancellationToken.None);

        // Assert
        Assert.False(capture.SawAuthorization);
        Assert.False(capture.SawProxyAuthorization);
        Assert.False(capture.SawCookie);
        Assert.False(capture.SawFoundryFeatures);
        credential.Verify(
            value => value.GetTokenAsync(It.IsAny<TokenRequestContext>(), It.IsAny<CancellationToken>()),
            Times.Never);
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

        var handler = new FoundryToolboxBearerTokenHandler(
            CreateMockCredential().Object,
            null,
            new Uri("https://example.com"))
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

    /// <summary>
    /// Captures whether credential-bearing headers reached the primary network handler.
    /// </summary>
    private sealed class HeaderCaptureHandler : HttpMessageHandler
    {
        public bool SawAuthorization { get; private set; }

        public bool SawProxyAuthorization { get; private set; }

        public bool SawCookie { get; private set; }

        public bool SawFoundryFeatures { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            this.SawAuthorization = request.Headers.Contains("Authorization");
            this.SawProxyAuthorization = request.Headers.Contains("Proxy-Authorization");
            this.SawCookie = request.Headers.Contains("Cookie");
            this.SawFoundryFeatures = request.Headers.Contains("Foundry-Features");
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
        }
    }

    /// <summary>
    /// An in-memory MCP peer that forces AutoDetect to legacy SSE and advertises a
    /// server-selected endpoint on a different origin.
    /// </summary>
    private sealed class CrossOriginSseHandler(Uri trustedEndpoint, Uri foreignEndpoint) : HttpMessageHandler
    {
        public bool SawStreamableHttpProbe { get; private set; }

        public bool SawLegacySseFallback { get; private set; }

        public bool SawForeignEndpointRequest { get; private set; }

        public string? ForeignAuthorization { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            if (request.RequestUri == foreignEndpoint)
            {
                this.SawForeignEndpointRequest = true;
                this.ForeignAuthorization = request.Headers.Authorization?.Parameter;
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.InternalServerError));
            }

            Assert.Equal(trustedEndpoint, request.RequestUri);
            if (request.Method == HttpMethod.Post)
            {
                this.SawStreamableHttpProbe = true;
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.MethodNotAllowed));
            }

            Assert.Equal(HttpMethod.Get, request.Method);
            this.SawLegacySseFallback = true;
            return Task.FromResult(
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(
                        $"event: endpoint\ndata: {foreignEndpoint.AbsoluteUri}\n\n",
                        Encoding.UTF8,
                        "text/event-stream")
                });
        }
    }
}
