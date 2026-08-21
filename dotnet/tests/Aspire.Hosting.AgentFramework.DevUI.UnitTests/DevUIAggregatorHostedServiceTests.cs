// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using Aspire.Hosting.ApplicationModel;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Aspire.Hosting.AgentFramework.DevUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="DevUIAggregatorHostedService"/> class.
/// </summary>
public class DevUIAggregatorHostedServiceTests
{
    #region RewriteAgentIdInQueryString Tests

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString returns empty string when query string has no value.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_EmptyQueryString_ReturnsEmptyString()
    {
        // Arrange
        var queryString = QueryString.Empty;

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "writer");

        // Assert
        Assert.Equal(string.Empty, result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString rewrites agent_id to the un-prefixed value.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_WithPrefixedAgentId_RewritesToUnprefixed()
    {
        // Arrange
        var queryString = new QueryString("?agent_id=writer-agent%2Fwriter");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "writer");

        // Assert
        Assert.Contains("agent_id=writer", result);
        Assert.DoesNotContain("writer-agent", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString preserves other query parameters.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_WithOtherParams_PreservesOtherParams()
    {
        // Arrange
        var queryString = new QueryString("?agent_id=writer-agent%2Fwriter&conversation_id=123&page=5");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "writer");

        // Assert
        Assert.Contains("agent_id=writer", result);
        Assert.Contains("conversation_id=123", result);
        Assert.Contains("page=5", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString works when agent_id is not the first parameter.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_AgentIdNotFirst_StillRewrites()
    {
        // Arrange
        var queryString = new QueryString("?page=1&agent_id=editor-agent%2Feditor&limit=10");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "editor");

        // Assert
        Assert.Contains("agent_id=editor", result);
        Assert.DoesNotContain("editor-agent", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString handles special characters in actual agent ID.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_SpecialCharsInAgentId_UrlEncodesCorrectly()
    {
        // Arrange
        var queryString = new QueryString("?agent_id=prefix%2Fmy-agent");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "my-agent");

        // Assert
        // The result should contain the agent_id with the value properly encoded if needed
        Assert.Contains("agent_id=my-agent", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString handles an agent_id with no prefix.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_NoPrefix_SetsDirectly()
    {
        // Arrange
        var queryString = new QueryString("?agent_id=simple");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "new-value");

        // Assert
        Assert.Contains("agent_id=new-value", result);
        Assert.DoesNotContain("simple", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString adds agent_id even if not originally present.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_NoAgentId_AddsAgentId()
    {
        // Arrange
        var queryString = new QueryString("?page=1&limit=10");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "writer");

        // Assert
        Assert.Contains("agent_id=writer", result);
        Assert.Contains("page=1", result);
        Assert.Contains("limit=10", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString returns proper format starting with ?.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_ValidQuery_ReturnsQueryStringFormat()
    {
        // Arrange
        var queryString = new QueryString("?agent_id=test");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "writer");

        // Assert
        Assert.StartsWith("?", result);
    }

    #endregion

    #region Backend Resolution Behavior Tests

    /// <summary>
    /// Verifies that ResolveBackends returns empty dictionary when no annotations are present.
    /// These tests verify the expected behavior of the aggregator via the DevUI resource annotations.
    /// </summary>
    [Fact]
    public void DevUIResource_NoAnnotations_ResolveBackendsReturnsEmpty()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();
        var devui = builder.AddDevUI("devui");

        // Act
        var annotations = devui.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .ToList();

        // Assert - no AgentServiceAnnotation means no backends
        Assert.Empty(annotations);
    }

    /// <summary>
    /// Verifies that WithAgentService adds proper annotations for backend resolution.
    /// </summary>
    [Fact]
    public void WithAgentService_AddsAnnotation_ForBackendResolution()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();
        var devui = builder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(builder, "writer-agent");

        // Act
        devui.WithAgentService(agentService);

        // Assert
        var annotation = devui.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .FirstOrDefault();

        Assert.NotNull(annotation);
        Assert.Equal("writer-agent", annotation.AgentService.Name);
    }

    /// <summary>
    /// Verifies that custom EntityIdPrefix is properly stored in the annotation.
    /// </summary>
    [Fact]
    public void WithAgentService_CustomPrefix_StoresInAnnotation()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();
        var devui = builder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(builder, "writer-agent");

        // Act
        devui.WithAgentService(agentService, entityIdPrefix: "custom-writer");

        // Assert
        var annotation = devui.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .First();

        Assert.Equal("custom-writer", annotation.EntityIdPrefix);
    }

    /// <summary>
    /// Verifies that multiple agent services create multiple annotations for backend resolution.
    /// </summary>
    [Fact]
    public void WithAgentService_MultipleServices_CreatesMultipleAnnotations()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();
        var devui = builder.AddDevUI("devui");
        var writerService = CreateMockAgentServiceBuilder(builder, "writer-agent");
        var editorService = CreateMockAgentServiceBuilder(builder, "editor-agent");

        // Act
        devui.WithAgentService(writerService);
        devui.WithAgentService(editorService);

        // Assert
        var annotations = devui.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .ToList();

        Assert.Equal(2, annotations.Count);
        Assert.Contains(annotations, a => a.AgentService.Name == "writer-agent");
        Assert.Contains(annotations, a => a.AgentService.Name == "editor-agent");
    }

    #endregion

    #region Backend Endpoint Selection Tests

    /// <summary>
    /// Verifies that ResolveBackends prefers the HTTPS endpoint when both HTTP and HTTPS are allocated.
    /// </summary>
    [Fact]
    public void ResolveBackends_WithHttpAndHttpsEndpoints_PrefersHttps()
    {
        // Arrange
        var devui = new DevUIResource("devui");
        var agentService = new TestEndpointResource("writer-agent");
        AddAllocatedEndpoint(agentService, "http", "http", 5050);
        AddAllocatedEndpoint(agentService, "https", "https", 7443);
        devui.Annotations.Add(new AgentServiceAnnotation(agentService));
        var aggregator = new DevUIAggregatorHostedService(devui, NullLogger.Instance);

        // Act
        var backends = aggregator.ResolveBackends();

        // Assert
        Assert.Equal("https://localhost:7443", backends["writer-agent"]);
    }

    /// <summary>
    /// Verifies that ResolveBackends falls back to HTTP when the HTTPS endpoint is not present.
    /// </summary>
    [Fact]
    public void ResolveBackends_WithOnlyHttpEndpoint_UsesHttp()
    {
        // Arrange
        var devui = new DevUIResource("devui");
        var agentService = new TestEndpointResource("writer-agent");
        AddAllocatedEndpoint(agentService, "http", "http", 5050);
        devui.Annotations.Add(new AgentServiceAnnotation(agentService));
        var aggregator = new DevUIAggregatorHostedService(devui, NullLogger.Instance);

        // Act
        var backends = aggregator.ResolveBackends();

        // Assert
        Assert.Equal("http://localhost:5050", backends["writer-agent"]);
    }

    /// <summary>
    /// Verifies that ResolveBackends falls back to HTTP when the HTTPS endpoint has not been allocated yet.
    /// </summary>
    [Fact]
    public void ResolveBackends_WithUnallocatedHttpsEndpoint_UsesHttp()
    {
        // Arrange
        var devui = new DevUIResource("devui");
        var agentService = new TestEndpointResource("writer-agent");
        AddEndpoint(agentService, "https", "https");
        AddAllocatedEndpoint(agentService, "http", "http", 5050);
        devui.Annotations.Add(new AgentServiceAnnotation(agentService));
        var aggregator = new DevUIAggregatorHostedService(devui, NullLogger.Instance);

        // Act
        var backends = aggregator.ResolveBackends();

        // Assert
        Assert.Equal("http://localhost:5050", backends["writer-agent"]);
    }

    #endregion

    #region Entity ID Parsing Tests

    /// <summary>
    /// Verifies the expected format for prefixed entity IDs in the aggregator.
    /// </summary>
    [Theory]
    [InlineData("writer-agent/writer", "writer-agent", "writer")]
    [InlineData("editor-agent/editor", "editor-agent", "editor")]
    [InlineData("custom/my-agent", "custom", "my-agent")]
    [InlineData("prefix/sub/path", "prefix", "sub/path")]
    public void PrefixedEntityId_Format_ExtractsCorrectly(string prefixedId, string expectedPrefix, string expectedRest)
    {
        // This test documents the expected format for prefixed entity IDs
        // The aggregator uses "prefix/entityId" format where:
        // - prefix is typically the resource name or custom prefix
        // - entityId is the original entity identifier from the backend

        // Act
        var slashIndex = prefixedId.IndexOf('/');
        var prefix = prefixedId[..slashIndex];
        var rest = prefixedId[(slashIndex + 1)..];

        // Assert
        Assert.Equal(expectedPrefix, prefix);
        Assert.Equal(expectedRest, rest);
    }

    #endregion

    #region Helper Methods

    /// <summary>
    /// Creates a mock agent service builder for testing.
    /// Uses a minimal resource implementation that satisfies IResourceWithEndpoints.
    /// </summary>
    private static IResourceBuilder<IResourceWithEndpoints> CreateMockAgentServiceBuilder(
        IDistributedApplicationBuilder appBuilder,
        string name)
    {
        // Create a mock resource that implements IResourceWithEndpoints
        var mockResource = new Moq.Mock<IResourceWithEndpoints>();
        mockResource.Setup(r => r.Name).Returns(name);
        mockResource.Setup(r => r.Annotations).Returns(new ResourceAnnotationCollection());

        var mockBuilder = new Moq.Mock<IResourceBuilder<IResourceWithEndpoints>>();
        mockBuilder.Setup(b => b.Resource).Returns(mockResource.Object);
        mockBuilder.Setup(b => b.ApplicationBuilder).Returns(appBuilder);

        return mockBuilder.Object;
    }

    private static void AddAllocatedEndpoint(
        TestEndpointResource resource,
        string name,
        string uriScheme,
        int port)
    {
        var endpoint = AddEndpoint(resource, name, uriScheme);
        endpoint.AllocatedEndpoint = new AllocatedEndpoint(endpoint, "localhost", port);
    }

    private static EndpointAnnotation AddEndpoint(
        TestEndpointResource resource,
        string name,
        string uriScheme)
    {
        var endpoint = new EndpointAnnotation(
            ProtocolType.Tcp,
            uriScheme: uriScheme,
            name: name,
            port: null,
            isProxied: false);

        resource.Annotations.Add(endpoint);
        return endpoint;
    }

    private sealed class TestEndpointResource(string name) : Resource(name), IResourceWithEndpoints;

    #endregion

    #region Proxy Target Validation Tests

    [Theory]
    [InlineData("http://localhost:5000", "/v1/conversations")]
    [InlineData("http://localhost:5000", "/devui/index.html?v=1")]
    public void ValidateProxyTarget_TargetStaysOnConfiguredBackend_ReturnsTargetUri(string backendUrl, string path)
    {
        // Arrange
        var backendUri = new Uri(backendUrl);

        // Act
        var target = DevUIAggregatorHostedService.ValidateProxyTarget(backendUrl, path);

        // Assert
        Assert.NotNull(target);
        Assert.Equal(backendUri.Host, target!.Host);
        Assert.Equal(backendUri.Scheme, target.Scheme);
        Assert.Equal(backendUri.Port, target.Port);
    }

    [Theory]
    [InlineData("http://localhost:5000", "http://alternate.example/data")] // absolute path overrides the host
    [InlineData("http://localhost:5000", "//alternate.example/data")]      // protocol-relative path overrides the host
    [InlineData("http://localhost:5000", "https://localhost:5000/data")]   // scheme differs from the backend
    [InlineData("http://localhost:5000", "http://localhost:6000/data")]    // port differs from the backend
    [InlineData("this is not a url", "/v1/conversations")]                 // malformed backend url
    public void ValidateProxyTarget_TargetLeavesConfiguredBackend_ReturnsNull(string backendUrl, string path)
    {
        // Act
        var target = DevUIAggregatorHostedService.ValidateProxyTarget(backendUrl, path);

        // Assert
        Assert.Null(target);
    }

    [Fact]
    public async Task ProxyRequest_ConversationRoute_ForwardsToConfiguredBackendAsync()
    {
        // Arrange
        await using var proxy = await ProxyTestContext.StartAsync();

        // Act
        var response = await proxy.SendAsync("/v1/conversations?limit=10");

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var forwarded = Assert.Single(proxy.BackendRequests);
        Assert.Equal("/v1/conversations", forwarded.Path);
        Assert.Equal("?limit=10", forwarded.QueryString);
    }

    [Fact]
    public async Task ProxyRequest_DevUIRoute_ForwardsToConfiguredBackendAsync()
    {
        // Arrange
        await using var proxy = await ProxyTestContext.StartAsync();

        // Act
        var response = await proxy.SendAsync("/devui/index.html?v=1");

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var forwarded = Assert.Single(proxy.BackendRequests);
        Assert.Equal("/devui/index.html", forwarded.Path);
        Assert.Equal("?v=1", forwarded.QueryString);
    }

    [Theory]
    [InlineData("/v1/conversations/../conversations")]
    [InlineData("/devui/../devui/index.html")]
    public async Task ProxyRequest_NormalizedPath_ForwardsToConfiguredBackendAsync(string requestPath)
    {
        // Arrange
        await using var proxy = await ProxyTestContext.StartAsync();

        // Act
        var response = await proxy.SendAsync(requestPath);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Single(proxy.BackendRequests);
    }

    #region Proxy Test Helpers

    /// <summary>
    /// Hosts a stub backend together with a DevUI aggregator wired to it, and exposes an
    /// <see cref="HttpClient"/> targeting the aggregator so proxied requests can be observed
    /// on the backend.
    /// </summary>
    private sealed class ProxyTestContext : IAsyncDisposable
    {
        private readonly WebApplication _backend;
        private readonly DevUIAggregatorHostedService _aggregator;
        private readonly HttpClient _client;
        private readonly List<(string Path, string QueryString)> _backendRequests;

        private ProxyTestContext(
            WebApplication backend,
            DevUIAggregatorHostedService aggregator,
            HttpClient client,
            List<(string Path, string QueryString)> backendRequests)
        {
            this._backend = backend;
            this._aggregator = aggregator;
            this._client = client;
            this._backendRequests = backendRequests;
        }

        /// <summary>Gets the requests received by the stub backend, in arrival order.</summary>
        public IReadOnlyList<(string Path, string QueryString)> BackendRequests => this._backendRequests;

        public static async Task<ProxyTestContext> StartAsync()
        {
            var backendRequests = new List<(string Path, string QueryString)>();
            var backend = await StartStubBackendAsync(backendRequests).ConfigureAwait(false);

            var aggregator = await StartAggregatorAsync(GetBaseAddress(backend)).ConfigureAwait(false);
            var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{aggregator.AllocatedPort}") };

            return new ProxyTestContext(backend, aggregator, client, backendRequests);
        }

        /// <summary>Sends a GET request to the aggregator using the given relative path.</summary>
        public Task<HttpResponseMessage> SendAsync(string relativePath)
            => this._client.GetAsync(new Uri(relativePath, UriKind.Relative));

        public async ValueTask DisposeAsync()
        {
            this._client.Dispose();
            await this._aggregator.DisposeAsync().ConfigureAwait(false);
            await this._backend.StopAsync().ConfigureAwait(false);
            await this._backend.DisposeAsync().ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Starts a minimal backend that records the path and query string of every request it receives.
    /// </summary>
    private static async Task<WebApplication> StartStubBackendAsync(List<(string Path, string QueryString)> requests)
    {
        var builder = WebApplication.CreateSlimBuilder();
        builder.Logging.ClearProviders();

        var app = builder.Build();
        app.Urls.Add("http://127.0.0.1:0");
        app.Map("{**path}", (HttpContext context) =>
        {
            requests.Add((context.Request.Path.Value ?? string.Empty, context.Request.QueryString.Value ?? string.Empty));
            return Results.Json(new { ok = true });
        });

        await app.StartAsync().ConfigureAwait(false);
        return app;
    }

    /// <summary>
    /// Starts a DevUI aggregator configured with a single backend pointing at <paramref name="backendUrl"/>.
    /// </summary>
    private static async Task<DevUIAggregatorHostedService> StartAggregatorAsync(string backendUrl)
    {
        var resource = new DevUIResource("test-devui");
        resource.Annotations.Add(new AgentServiceAnnotation(CreateBackendResource(backendUrl)));

        using var loggerFactory = LoggerFactory.Create(_ => { });
        var aggregator = new DevUIAggregatorHostedService(
            resource,
            loggerFactory.CreateLogger<DevUIAggregatorHostedService>());

        await aggregator.StartAsync(CancellationToken.None).ConfigureAwait(false);
        return aggregator;
    }

    /// <summary>
    /// Creates a backend resource whose "http" endpoint is allocated to <paramref name="backendUrl"/>.
    /// </summary>
    private static TestBackendResource CreateBackendResource(string backendUrl)
    {
        var backendUri = new Uri(backendUrl);
        var resource = new TestBackendResource("test-backend");

        var endpoint = new EndpointAnnotation(
            ProtocolType.Tcp,
            uriScheme: "http",
            name: "http",
            port: backendUri.Port,
            isProxied: false)
        {
            TargetHost = backendUri.Host
        };
        endpoint.AllocatedEndpoint = new AllocatedEndpoint(endpoint, backendUri.Host, backendUri.Port);

        resource.Annotations.Add(endpoint);
        return resource;
    }

    private static string GetBaseAddress(WebApplication app)
        => app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.First();

    private sealed class TestBackendResource(string name) : Resource(name), IResourceWithEndpoints;

    #endregion

    #endregion
}
