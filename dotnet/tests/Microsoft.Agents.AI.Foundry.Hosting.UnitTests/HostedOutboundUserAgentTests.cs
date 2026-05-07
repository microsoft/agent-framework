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
        // foundry-hosting/agent-framework-dotnet/{version} supplement on its User-Agent.
        // (We don't care about the inbound response shape — only that the agent's call to MEAI
        // triggered an outbound request whose UA reaches the sandbox boundary correctly.)
        Assert.True(this._outboundHandler!.Requests.Count > 0,
            $"Expected at least one outbound request. Inbound status: {(int)inboundResponse.StatusCode}, body: {inboundBody}");
        var outbound = this._outboundHandler.Requests[0];
        Assert.StartsWith(TestEndpoint, outbound.Uri);
        Assert.Contains("MEAI/", outbound.UserAgent);
        Assert.Contains("foundry-hosting/agent-framework-dotnet", outbound.UserAgent);
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
