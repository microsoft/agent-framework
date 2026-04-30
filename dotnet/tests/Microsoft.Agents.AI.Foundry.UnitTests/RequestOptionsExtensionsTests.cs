// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Verifies the per-call <c>MeaiUserAgentPolicy</c> exposed via
/// <see cref="RequestOptionsExtensions.UserAgentPolicy"/>. The policy is reachable through the
/// public <see cref="FoundryAgent"/> constructors (which add it to the internally-built
/// <see cref="Azure.AI.Projects.AIProjectClient"/>'s pipeline), so its behavior is part of the
/// public API surface.
/// </summary>
public sealed class RequestOptionsExtensionsTests
{
    [Fact]
    public async Task MeaiUserAgentPolicy_AddsMeaiSegment_ToOutgoingRequestAsync()
    {
        // Arrange
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(httpClient) },
            perCallPolicies: [RequestOptionsExtensions.UserAgentPolicy],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act
        var message = pipeline.CreateMessage();
        message.Request.Method = "POST";
        message.Request.Uri = new System.Uri("https://example.test/anything");
        await pipeline.SendAsync(message);

        // Assert
        Assert.Equal(1, handler.Count);
        Assert.NotNull(handler.LastUserAgent);
        Assert.Contains("MEAI/", handler.LastUserAgent);
    }

    [Fact]
    public async Task MeaiUserAgentPolicy_DoesNotAddFoundryHostingSegmentAsync()
    {
        // Arrange
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(httpClient) },
            perCallPolicies: [RequestOptionsExtensions.UserAgentPolicy],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act
        var message = pipeline.CreateMessage();
        message.Request.Method = "POST";
        message.Request.Uri = new System.Uri("https://example.test/anything");
        await pipeline.SendAsync(message);

        // Assert: the policy is MEAI-only; the foundry-hosting supplement is added elsewhere
        // (by the polyfill DelegatingResponsesClient → HostedAgentUserAgentPolicy).
        Assert.NotNull(handler.LastUserAgent);
        Assert.DoesNotContain("foundry-hosting/agent-framework-dotnet", handler.LastUserAgent);
    }

    [Fact]
    public void UserAgentPolicy_ExposesSingletonInstance()
    {
        // Two reads of the static property must return the same instance — the policy is stateless and shared.
        var first = RequestOptionsExtensions.UserAgentPolicy;
        var second = RequestOptionsExtensions.UserAgentPolicy;
        Assert.Same(first, second);
    }

    [Fact]
    public void MeaiUserAgentPolicy_ValueIncludesAFFoundryAssemblyVersion_ReflectionGuard()
    {
        // The policy emits "MEAI/{Microsoft.Agents.AI.Foundry assembly InformationalVersion}".
        // If the assembly metadata stops being readable, the policy falls back to "MEAI" without a version,
        // which is a measurable telemetry regression.
        var attr = typeof(RequestOptionsExtensions).Assembly
            .GetCustomAttribute<AssemblyInformationalVersionAttribute>();
        Assert.NotNull(attr);
        Assert.False(string.IsNullOrEmpty(attr!.InformationalVersion));
    }

    private sealed class RecordingHandler : HttpClientHandler
    {
        public int Count { get; private set; }
        public string? LastUserAgent { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this.Count++;
            this.LastUserAgent = request.Headers.TryGetValues("User-Agent", out var values)
                ? string.Join(",", values)
                : null;

            var resp = new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{}", Encoding.UTF8, "application/json"),
                RequestMessage = request,
            };
            return Task.FromResult(resp);
        }
    }
}
