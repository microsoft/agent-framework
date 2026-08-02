// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Verifies the framework-wide <see cref="AgentFrameworkUserAgentPolicy"/>. The policy stamps
/// <c>agent-framework-dotnet/{version}</c> onto the outgoing <c>User-Agent</c> header of every
/// request made through a Foundry chat client and is registered automatically by
/// <c>FoundryChatClient</c> via the MEAI <c>OpenAIRequestPolicies</c> hook.
/// </summary>
public sealed class AgentFrameworkUserAgentPolicyTests
{
    [Fact]
    public async Task AgentFrameworkUserAgentPolicy_AddsAgentFrameworkSegment_ToOutgoingRequestAsync()
    {
        // Arrange
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(httpClient) },
            perCallPolicies: [AgentFrameworkUserAgentPolicy.Instance],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act
        var message = pipeline.CreateMessage();
        message.Request.Method = "POST";
        message.Request.Uri = new Uri("https://example.test/anything");
        await pipeline.SendAsync(message);

        // Assert
        Assert.Equal(1, handler.Count);
        Assert.NotNull(handler.LastUserAgent);
        Assert.Contains("agent-framework-dotnet/", handler.LastUserAgent);
    }

    [Fact]
    public async Task AgentFrameworkUserAgentPolicy_DoesNotStampMeaiSegmentAsync()
    {
        // Arrange: the AF policy must only contribute the agent-framework-dotnet segment.
        // The MEAI/{version} segment is contributed by the MEAI-shipped policy at a different
        // layer; this policy must not duplicate or replace it.
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(httpClient) },
            perCallPolicies: [AgentFrameworkUserAgentPolicy.Instance],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act
        var message = pipeline.CreateMessage();
        message.Request.Method = "POST";
        message.Request.Uri = new Uri("https://example.test/anything");
        await pipeline.SendAsync(message);

        // Assert
        Assert.NotNull(handler.LastUserAgent);
        Assert.DoesNotContain("MEAI/", handler.LastUserAgent);
        Assert.DoesNotContain("foundry-hosting/", handler.LastUserAgent);
    }

    [Fact]
    public async Task AgentFrameworkUserAgentPolicy_PreservesExistingUserAgent_WhenAppendingAsync()
    {
        // Arrange: a per-call policy upstream that pre-populates the User-Agent header. The AF
        // policy must read the existing value and append (not overwrite) the agent-framework
        // segment so both stay reachable on the wire. (The exact separator the HTTP transport
        // emits between multi-value User-Agent entries is comma per RFC 7230; this test does
        // not assert on the separator character because that is a transport detail.)
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(httpClient) },
            perCallPolicies: [new SeedUserAgentPolicy("existing-app/1.0"), AgentFrameworkUserAgentPolicy.Instance],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act
        var message = pipeline.CreateMessage();
        message.Request.Method = "POST";
        message.Request.Uri = new Uri("https://example.test/anything");
        await pipeline.SendAsync(message);

        // Assert: both segments survive to the wire.
        Assert.NotNull(handler.LastUserAgent);
        Assert.Contains("existing-app/1.0", handler.LastUserAgent);
        Assert.Contains("agent-framework-dotnet/", handler.LastUserAgent);
    }

    [Fact]
    public async Task AgentFrameworkUserAgentPolicy_IsIdempotent_DoesNotDoubleStampAsync()
    {
        // Arrange: register the same policy twice on the same pipeline. The second application
        // must detect the segment is already present and not append it again. Guards against
        // double-stamping on retries or duplicate registration.
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(httpClient) },
            perCallPolicies: [AgentFrameworkUserAgentPolicy.Instance, AgentFrameworkUserAgentPolicy.Instance],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act
        var message = pipeline.CreateMessage();
        message.Request.Method = "POST";
        message.Request.Uri = new Uri("https://example.test/anything");
        await pipeline.SendAsync(message);

        // Assert: exactly one occurrence of "agent-framework-dotnet/".
        Assert.NotNull(handler.LastUserAgent);
        var ua = handler.LastUserAgent!;
        var first = ua.IndexOf("agent-framework-dotnet/", StringComparison.Ordinal);
        Assert.True(first >= 0, "Expected at least one agent-framework-dotnet segment.");
        var second = ua.IndexOf("agent-framework-dotnet/", first + 1, StringComparison.Ordinal);
        Assert.Equal(-1, second);
    }

    [Fact]
    public void AgentFrameworkUserAgentPolicy_ExposesSingletonInstance()
    {
        // Two reads of the static property must return the same instance. The policy is stateless
        // and shared; allocating a fresh instance per registration site would bloat memory and
        // defeat the dedup logic in OpenAIRequestPoliciesReflection.AddPolicyIfMissing.
        var first = AgentFrameworkUserAgentPolicy.Instance;
        var second = AgentFrameworkUserAgentPolicy.Instance;
        Assert.Same(first, second);
    }

    [Fact]
    public void AgentFrameworkUserAgentPolicy_ValueIncludesAFFoundryAssemblyVersion_ReflectionGuard()
    {
        // The policy emits "agent-framework-dotnet/{Microsoft.Agents.AI.Foundry assembly InformationalVersion}".
        // If the assembly metadata stops being readable, the policy falls back to "agent-framework-dotnet"
        // without a version, which is a measurable telemetry regression.
        var attr = typeof(AgentFrameworkUserAgentPolicy).Assembly
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

    private sealed class SeedUserAgentPolicy : PipelinePolicy
    {
        private readonly string _value;
        public SeedUserAgentPolicy(string value) => this._value = value;

        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set("User-Agent", this._value);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set("User-Agent", this._value);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }
    }
}
