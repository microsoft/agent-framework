// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using OpenAI;

#pragma warning disable OPENAI001, SCME0001, SCME0002, MEAI001

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// End-to-end tests that exercise the FULL hosted ASP.NET Core pipeline:
/// inbound HTTP → MapFoundryResponses → AgentFrameworkResponseHandler → TryApplyUserAgent →
/// agent invocation → outbound HTTP from inside the hosted environment.
/// Verifies that the hosted-agent <c>User-Agent</c> supplement reaches the outbound wire,
/// not just the inbound request.
/// </summary>
public sealed class HostedOutboundUserAgentTests : IAsyncDisposable
{
    private const string TestEndpoint = "https://fake-foundry.example.com/api/projects/fake-prj";
    private const string Deployment = "fake-deployment";

    private WebApplication? _app;
    private HttpClient? _inboundClient;
    private RecordingHandler? _outboundHandler;

    public async ValueTask DisposeAsync()
    {
        this._inboundClient?.Dispose();
        this._outboundHandler?.Dispose();
        if (this._app is not null)
        {
            await this._app.DisposeAsync();
        }
    }

    [Fact]
    public async Task Hosted_InboundResponsesRequest_TriggersOutboundCall_WithFoundryHostingSupplementAsync()
    {
        // Arrange: spin up a real ASP.NET Core TestServer that hosts an AIAgent backed by MEAI's
        // OpenAIResponsesChatClient → ProjectResponsesClient → fake HTTP transport. This is the
        // exact production stack minus the network: the only thing not real is the wire transport.
        await this.StartHostedServerAsync();

        // Act: send an inbound /openai/v1/responses request as the Foundry runtime would.
        using var inboundRequest = new HttpRequestMessage(HttpMethod.Post, "/responses")
        {
            Content = new StringContent(InboundResponsesRequestJson(), Encoding.UTF8, "application/json"),
        };
        using var inboundResponse = await this._inboundClient!.SendAsync(inboundRequest);
        var inboundBody = await inboundResponse.Content.ReadAsStringAsync();

        // Assert: at least one OUTBOUND request reached the fake transport, AND it carries the
        // combined hosted segment foundry-hosting/agent-framework-dotnet/{version} on its
        // User-Agent. This matches Python's contract
        // (foundry-hosting/agent-framework-python/{version}, see
        // python/packages/core/agent_framework/_telemetry.py): a single combined segment when
        // hosted, never two separate ones. The bare agent-framework-dotnet/{version} segment
        // (from AgentFrameworkUserAgentPolicy in FoundryChatClient) must be upgraded in place
        // by HostedAgentUserAgentPolicy — never appear duplicated.
        Assert.True(this._outboundHandler!.Requests.Count > 0,
            $"Expected at least one outbound request. Inbound status: {(int)inboundResponse.StatusCode}, body: {inboundBody}");
        var outbound = this._outboundHandler.Requests[0];
        Assert.StartsWith(TestEndpoint, outbound.Uri);
        Assert.Contains("MEAI/", outbound.UserAgent);
        Assert.Contains("foundry-hosting/agent-framework-dotnet/", outbound.UserAgent);

        // The bare agent-framework-dotnet/{v} segment must NOT appear separately when the
        // combined form is present — Python emits a single combined value when the hosted
        // prefix is registered, and .NET preserves that contract via the in-place upgrade in
        // HostedAgentUserAgentPolicy.
        var combinedIdx = outbound.UserAgent!.IndexOf("foundry-hosting/agent-framework-dotnet/", StringComparison.Ordinal);
        var beforeCombined = outbound.UserAgent.Substring(0, combinedIdx);
        var afterCombined = outbound.UserAgent.Substring(combinedIdx + "foundry-hosting/agent-framework-dotnet/".Length);
        Assert.DoesNotContain("agent-framework-dotnet/", beforeCombined);
        Assert.DoesNotContain("agent-framework-dotnet/", afterCombined);
    }

    private async Task StartHostedServerAsync()
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        // Build a real ChatClientAgent whose IChatClient is MEAI's OpenAIResponsesChatClient
        // wrapping a ProjectResponsesClient backed by a fake HTTP handler. After AgentFrameworkResponseHandler
        // resolves this agent, TryApplyUserAgent will swap the inner _responseClient with our wrapper.
        this._outboundHandler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        var outboundHttpClient = new HttpClient(this._outboundHandler);
#pragma warning restore CA5399

        var projectOptions = new ProjectResponsesClientOptions
        {
            Transport = new HttpClientPipelineTransport(outboundHttpClient),
        };
        var projectResponsesClient = new ProjectResponsesClient(
            new Uri(TestEndpoint),
            new FakeAuthenticationTokenProvider(),
            projectOptions);

        IChatClient chatClient = projectResponsesClient.AsIChatClient(Deployment);
        AIAgent agent = new ChatClientAgent(chatClient);

        builder.Services.AddFoundryResponses(agent);
        builder.Services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        builder.Services.AddLogging();

        this._app = builder.Build();
        this._app.MapFoundryResponses();

        await this._app.StartAsync();

        var testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._inboundClient = testServer.CreateClient();
    }

    private static string InboundResponsesRequestJson() => """
        {
          "model": "fake-deployment",
          "input": [
            {
              "type": "message",
              "id": "msg_1",
              "status": "completed",
              "role": "user",
              "content": [{ "type": "input_text", "text": "Hello" }]
            }
          ]
        }
        """;

    private static string MinimalResponseJson() => """
        {
          "id":"resp_1","object":"response","created_at":1700000000,"status":"completed",
          "model":"fake","output":[],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}
        }
        """;

    [Fact]
    public void TryApplyUserAgent_RepeatedCalls_OnSameAgent_RegistersPolicyOnce()
    {
        // Arrange: hosted resolution calls TryApplyUserAgent on every request. Without per-instance
        // dedup, each call would append another policy entry to the shared OpenAIRequestPolicies,
        // producing unbounded growth on singleton agents (one chat client reused across requests).
        using var http = new HttpClient(new NoopHandler());
        var openAIClient = new OpenAIClient(new ApiKeyCredential("fake"),
            new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http) });
        IChatClient chatClient = openAIClient.GetResponsesClient().AsIChatClient();
        AIAgent agent = new ChatClientAgent(chatClient);

        // Act
        for (int i = 0; i < 50; i++)
        {
            FoundryHostingExtensions.TryApplyUserAgent(agent);
        }

        // Assert: exactly one HostedAgentUserAgentPolicy entry on the shared OpenAIRequestPolicies.
        var policies = chatClient.GetService<OpenAIRequestPolicies>();
        Assert.NotNull(policies);
        Assert.Equal(1, EntriesCount(policies!));
    }

    [Fact]
    public void TryApplyUserAgent_AcrossDistinctAgents_RegistersPolicyOncePerChatClient()
    {
        // Arrange: dedup is per-OpenAIRequestPolicies-instance, not global, so two agents on
        // different chat clients each get exactly one registration.
        using var http1 = new HttpClient(new NoopHandler());
        using var http2 = new HttpClient(new NoopHandler());
        var client1 = new OpenAIClient(new ApiKeyCredential("k1"),
            new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http1) });
        var client2 = new OpenAIClient(new ApiKeyCredential("k2"),
            new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http2) });

        IChatClient cc1 = client1.GetResponsesClient().AsIChatClient();
        IChatClient cc2 = client2.GetResponsesClient().AsIChatClient();
        AIAgent a1 = new ChatClientAgent(cc1);
        AIAgent a2 = new ChatClientAgent(cc2);

        // Act
        for (int i = 0; i < 10; i++)
        {
            FoundryHostingExtensions.TryApplyUserAgent(a1);
            FoundryHostingExtensions.TryApplyUserAgent(a2);
        }

        // Assert
        Assert.Equal(1, EntriesCount(cc1.GetService<OpenAIRequestPolicies>()!));
        Assert.Equal(1, EntriesCount(cc2.GetService<OpenAIRequestPolicies>()!));
    }

    private static int EntriesCount(OpenAIRequestPolicies policies)
    {
        var field = typeof(OpenAIRequestPolicies).GetField("_entries", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
        var array = (Array?)field?.GetValue(policies);
        return array?.Length ?? -1;
    }

    // -----------------------------------------------------------------------
    // Direct unit tests for HostedAgentUserAgentPolicy's in-place upgrade behavior.
    // These run the policy on a synthetic ClientPipeline (no hosting infrastructure)
    // so the upgrade logic itself can be asserted in isolation.
    // -----------------------------------------------------------------------

    [Fact]
    public async Task HostedAgentUserAgentPolicy_UpgradesBareAgentFrameworkSegment_InPlaceAsync()
    {
        // Arrange: an upstream per-call policy stamps the bare agent-framework-dotnet/{version}
        // segment (matching what AgentFrameworkUserAgentPolicy would write in non-hosted code).
        // Then HostedAgentUserAgentPolicy runs and must REPLACE that segment with the combined
        // foundry-hosting/agent-framework-dotnet/{version} form, not append a duplicate.
        using var handler = new InspectingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399

        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(httpClient) },
            perCallPolicies: [new SetUserAgentPolicy("agent-framework-dotnet/9.9.9"), HostedAgentUserAgentPolicy.Instance],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act
        var message = pipeline.CreateMessage();
        message.Request.Method = "POST";
        message.Request.Uri = new Uri("https://example.test/anything");
        await pipeline.SendAsync(message);

        // Assert: combined form is present; bare form is gone (no duplicate agent-framework segment).
        Assert.NotNull(handler.LastUserAgent);
        Assert.Contains("foundry-hosting/agent-framework-dotnet/", handler.LastUserAgent);
        var ua = handler.LastUserAgent!;
        var firstAgentFramework = ua.IndexOf("agent-framework-dotnet/", StringComparison.Ordinal);
        Assert.True(firstAgentFramework >= 0, "Expected agent-framework-dotnet segment.");
        var secondAgentFramework = ua.IndexOf("agent-framework-dotnet/", firstAgentFramework + 1, StringComparison.Ordinal);
        Assert.Equal(-1, secondAgentFramework);
    }

    [Fact]
    public async Task HostedAgentUserAgentPolicy_AppendsCombined_WhenNoBareSegmentPresentAsync()
    {
        // Arrange: nothing upstream stamps the bare segment. Hosted policy should append the
        // full combined segment to whatever User-Agent is on the wire.
        using var handler = new InspectingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399

        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(httpClient) },
            perCallPolicies: [HostedAgentUserAgentPolicy.Instance],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act
        var message = pipeline.CreateMessage();
        message.Request.Method = "POST";
        message.Request.Uri = new Uri("https://example.test/anything");
        await pipeline.SendAsync(message);

        // Assert
        Assert.NotNull(handler.LastUserAgent);
        Assert.Contains("foundry-hosting/agent-framework-dotnet/", handler.LastUserAgent);
    }

    [Fact]
    public async Task HostedAgentUserAgentPolicy_IsIdempotent_WhenCombinedSegmentAlreadyPresentAsync()
    {
        // Arrange: upstream pre-populates the combined segment (simulating a retry or duplicate
        // registration). Hosted policy must not re-append.
        using var handler = new InspectingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399

        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(httpClient) },
            perCallPolicies: [new SetUserAgentPolicy("foundry-hosting/agent-framework-dotnet/9.9.9"), HostedAgentUserAgentPolicy.Instance],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act
        var message = pipeline.CreateMessage();
        message.Request.Method = "POST";
        message.Request.Uri = new Uri("https://example.test/anything");
        await pipeline.SendAsync(message);

        // Assert: exactly one occurrence of "foundry-hosting/agent-framework-dotnet/" segment.
        Assert.NotNull(handler.LastUserAgent);
        var first = handler.LastUserAgent!.IndexOf("foundry-hosting/agent-framework-dotnet/", StringComparison.Ordinal);
        Assert.True(first >= 0);
        var second = handler.LastUserAgent.IndexOf("foundry-hosting/agent-framework-dotnet/", first + 1, StringComparison.Ordinal);
        Assert.Equal(-1, second);
    }

    [Fact]
    public async Task HostedAgentUserAgentPolicy_ReplacesDifferentVersionCombinedSegment_InPlaceAsync()
    {
        // Q-D regression: when the User-Agent already carries the COMBINED hosted form with a
        // different version (e.g. an older registration or caller-supplied baseline), the policy
        // must replace the entire combined span — not just the bare suffix — so we never emit
        // the malformed `foundry-hosting/foundry-hosting/agent-framework-dotnet/...` shape.
        using var handler = new InspectingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399

        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(httpClient) },
            perCallPolicies: [new SetUserAgentPolicy("foundry-hosting/agent-framework-dotnet/0.0.1 MEAI/10.5.1"), HostedAgentUserAgentPolicy.Instance],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act
        var message = pipeline.CreateMessage();
        message.Request.Method = "POST";
        message.Request.Uri = new Uri("https://example.test/anything");
        await pipeline.SendAsync(message);

        // Assert: no doubled foundry-hosting/ prefix.
        Assert.NotNull(handler.LastUserAgent);
        Assert.DoesNotContain("foundry-hosting/foundry-hosting/", handler.LastUserAgent, StringComparison.Ordinal);

        // The combined segment must appear exactly once, and the trailing MEAI segment must be
        // preserved in place (i.e. the policy only rewrote the combined span, not anything after it).
        var firstCombined = handler.LastUserAgent!.IndexOf("foundry-hosting/agent-framework-dotnet/", StringComparison.Ordinal);
        Assert.True(firstCombined >= 0);
        var secondCombined = handler.LastUserAgent.IndexOf("foundry-hosting/agent-framework-dotnet/", firstCombined + 1, StringComparison.Ordinal);
        Assert.Equal(-1, secondCombined);
        Assert.Contains(" MEAI/10.5.1", handler.LastUserAgent, StringComparison.Ordinal);

        // And the version that survives must be the runtime supplement value's version, not 0.0.1.
        Assert.DoesNotContain("foundry-hosting/agent-framework-dotnet/0.0.1", handler.LastUserAgent, StringComparison.Ordinal);
    }

    private sealed class InspectingHandler : HttpClientHandler
    {
        public string? LastUserAgent { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this.LastUserAgent = request.Headers.TryGetValues("User-Agent", out var values)
                ? string.Join(",", values)
                : null;

            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{}", Encoding.UTF8, "application/json"),
                RequestMessage = request,
            });
        }
    }

    private sealed class SetUserAgentPolicy : PipelinePolicy
    {
        private readonly string _value;
        public SetUserAgentPolicy(string value) => this._value = value;

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

    private sealed class NoopHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
    }

    private sealed class RecordingHandler : HttpClientHandler
    {
        private readonly string _body;
        public List<RecordedRequest> Requests { get; } = [];

        public RecordingHandler(string body)
        {
            this._body = body;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string ua = request.Headers.TryGetValues("User-Agent", out var values)
                ? string.Join(",", values)
                : "(none)";
            this.Requests.Add(new RecordedRequest(request.RequestUri?.ToString() ?? "?", ua));

            var resp = new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(this._body, Encoding.UTF8, "application/json"),
                RequestMessage = request,
            };
            return Task.FromResult(resp);
        }
    }

    private readonly record struct RecordedRequest(string Uri, string UserAgent);
}
