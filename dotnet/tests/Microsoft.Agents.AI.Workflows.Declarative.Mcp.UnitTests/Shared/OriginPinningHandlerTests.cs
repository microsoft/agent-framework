// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp.UnitTests;

/// <summary>
/// Unit tests for the shared <see cref="OriginPinningHandler"/>.
/// </summary>
public sealed class OriginPinningHandlerTests
{
    private const string PinnedEndpoint = "https://trusted.example.com/mcp";

    [Fact]
    public void DefaultHeaderNames_ContainsCredentialHeaders()
    {
        // Arrange
        string[] expected = ["Authorization", "Proxy-Authorization", "Cookie"];

        // Assert
        Assert.Equal(expected, OriginPinningHandler.DefaultHeaderNames);
    }

    [Fact]
    public async Task SendAsync_SameOrigin_ForwardsDefaultHeadersAsync()
    {
        // Arrange
        using HttpRequestMessage request = CreateRequestWithCredentials("https://trusted.example.com/mcp/message");

        // Act
        IReadOnlyCollection<string> forwarded = await SendThroughHandlerAsync(request);

        // Assert: same-origin traffic keeps every credential header.
        Assert.Contains("Authorization", forwarded);
        Assert.Contains("Proxy-Authorization", forwarded);
        Assert.Contains("Cookie", forwarded);
    }

    [Theory]
    [InlineData("https://untrusted.example/collect")]
    [InlineData("https://trusted.example.com:8443/mcp")]
    [InlineData("http://trusted.example.com/mcp")]
    public async Task SendAsync_DifferentOrigin_RemovesDefaultHeadersAsync(string requestUri)
    {
        // Arrange: a different host, port, or scheme is a different origin.
        using HttpRequestMessage request = CreateRequestWithCredentials(requestUri);

        // Act
        IReadOnlyCollection<string> forwarded = await SendThroughHandlerAsync(request);

        // Assert: no credential header reaches the inner handler.
        Assert.DoesNotContain("Authorization", forwarded);
        Assert.DoesNotContain("Proxy-Authorization", forwarded);
        Assert.DoesNotContain("Cookie", forwarded);
    }

    [Fact]
    public async Task SendAsync_DifferentOrigin_PreservesOtherHeadersAsync()
    {
        // Arrange
        using HttpRequestMessage request = CreateRequestWithCredentials("https://untrusted.example/collect");
        request.Headers.TryAddWithoutValidation("X-Trace-Id", "trace-123");

        // Act
        IReadOnlyCollection<string> forwarded = await SendThroughHandlerAsync(request);

        // Assert: only the configured headers are removed.
        Assert.DoesNotContain("Authorization", forwarded);
        Assert.Contains("X-Trace-Id", forwarded);
    }

    [Fact]
    public async Task SendAsync_RelativeRequestUri_RetainsHeadersAsync()
    {
        // Arrange: HttpClient resolves a relative URI against its base address, so it cannot select
        // another origin by itself.
        using HttpRequestMessage request = new(HttpMethod.Post, new Uri("/mcp/message", UriKind.Relative));
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer test-credential");

        // Act
        IReadOnlyCollection<string> forwarded = await SendThroughHandlerAsync(request);

        // Assert
        Assert.Contains("Authorization", forwarded);
    }

    [Fact]
    public async Task SendAsync_CustomHeaderNames_RemovesOnlyConfiguredHeadersAsync()
    {
        // Arrange
        using HttpRequestMessage request = new(HttpMethod.Post, "https://untrusted.example/collect");
        request.Headers.TryAddWithoutValidation("X-Api-Key", "test-key");
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer test-credential");

        // Act
        IReadOnlyCollection<string> forwarded = await SendThroughHandlerAsync(request, headerNames: ["x-api-key"]);

        // Assert: configured names match case-insensitively and replace the default set.
        Assert.DoesNotContain("X-Api-Key", forwarded);
        Assert.Contains("Authorization", forwarded);
    }

    [Fact]
    public async Task SendAsync_CustomHeaderNames_SameOrigin_RetainsConfiguredHeadersAsync()
    {
        // Arrange
        using HttpRequestMessage request = new(HttpMethod.Post, "https://trusted.example.com/other");
        request.Headers.TryAddWithoutValidation("X-Api-Key", "test-key");

        // Act
        IReadOnlyCollection<string> forwarded = await SendThroughHandlerAsync(request, headerNames: ["X-Api-Key"]);

        // Assert
        Assert.Contains("X-Api-Key", forwarded);
    }

    [Theory]
    [InlineData("https://trusted.example.com/other", "https://trusted.example.com/mcp", true)]
    [InlineData("https://TRUSTED.Example.COM/mcp", "https://trusted.example.com/mcp", true)]
    [InlineData("https://trusted.example.com:443/mcp", "https://trusted.example.com/mcp", true)]
    [InlineData("https://trusted.example.com/mcp", "https://trusted.example.com:443/mcp", true)]
    [InlineData("http://trusted.example.com/mcp", "https://trusted.example.com/mcp", false)]
    [InlineData("https://trusted.example.com:8443/mcp", "https://trusted.example.com/mcp", false)]
    [InlineData("https://untrusted.example/mcp", "https://trusted.example.com/mcp", false)]
    public void IsSameOrigin_ComparesSchemeHostAndPort(string requestUri, string pinnedEndpoint, bool expected)
    {
        // Act
        bool actual = OriginPinningHandler.IsSameOrigin(new Uri(requestUri), new Uri(pinnedEndpoint));

        // Assert
        Assert.Equal(expected, actual);
    }

    [Fact]
    public void IsSameOrigin_MissingOrRelativeRequestUri_ReturnsTrue()
    {
        // Act & Assert
        Assert.True(OriginPinningHandler.IsSameOrigin(null, new Uri(PinnedEndpoint)));
        Assert.True(OriginPinningHandler.IsSameOrigin(new Uri("/mcp", UriKind.Relative), new Uri(PinnedEndpoint)));
    }

    [Fact]
    public void Constructor_NullEndpoint_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new OriginPinningHandler(null!));
    }

    [Fact]
    public void Constructor_RelativeEndpoint_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new OriginPinningHandler(new Uri("/mcp", UriKind.Relative)));
    }

    [Fact]
    public void Constructor_EmptyHeaderNames_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new OriginPinningHandler(new Uri(PinnedEndpoint), []));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    public void Constructor_InvalidHeaderName_Throws(string? headerName)
    {
        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() => new OriginPinningHandler(new Uri(PinnedEndpoint), [headerName!]));
    }

    private static HttpRequestMessage CreateRequestWithCredentials(string requestUri)
    {
        HttpRequestMessage request = new(HttpMethod.Post, requestUri);
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer test-credential");
        request.Headers.TryAddWithoutValidation("Proxy-Authorization", "Basic test-proxy");
        request.Headers.TryAddWithoutValidation("Cookie", "session=test");
        return request;
    }

    private static async Task<IReadOnlyCollection<string>> SendThroughHandlerAsync(
        HttpRequestMessage request,
        IEnumerable<string>? headerNames = null)
    {
        HeaderCaptureHandler capture = new();
        using OriginPinningHandler pinning = new(new Uri(PinnedEndpoint), headerNames) { InnerHandler = capture };
        using HttpMessageInvoker invoker = new(pinning);

        using HttpResponseMessage response = await invoker.SendAsync(request, CancellationToken.None);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        return capture.HeaderNames;
    }

    /// <summary>
    /// Records the request header names that reached the primary network handler.
    /// </summary>
    private sealed class HeaderCaptureHandler : HttpMessageHandler
    {
        public IReadOnlyCollection<string> HeaderNames { get; private set; } = [];

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this.HeaderNames = request.Headers.Select(header => header.Key).ToHashSet(StringComparer.OrdinalIgnoreCase);
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
        }
    }
}
