// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable OPENAI001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// One-shot verification (kept in tree to detect regressions) that MEAI 10.5.1 stamps its own
/// <c>MEAI/{version}</c> User-Agent segment automatically when an <see cref="ResponsesClient"/>
/// is wrapped via <c>AsIChatClient()</c>. If this test starts failing, the FoundryChatClient
/// implementation must re-register the MEAI policy explicitly via OpenAIRequestPolicies because
/// the local Foundry copy was deleted under the assumption that MEAI provides it built-in.
/// </summary>
public sealed class MeaiAutoUserAgentVerificationTests
{
    [Fact]
    public async Task MeaiOpenAIResponsesClient_StampsMeaiSegmentAutomatically_WithoutLocalPolicyAsync()
    {
        // Arrange: bare OpenAI ResponseClient over a fake HTTP transport, wrapped via MEAI's
        // AsIChatClient() with no custom OpenAIRequestPolicies registration. If MEAI auto-stamps
        // its own MEAI/{version} segment, it will appear here.
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399

        var options = new OpenAIClientOptions
        {
            Transport = new HttpClientPipelineTransport(httpClient),
            Endpoint = new Uri("https://example.test/v1"),
        };

        var responseClient = new ResponsesClient(new ApiKeyCredential("test-key"), options);
        var chatClient = responseClient.AsIChatClient("gpt-4o-mini");

        // Act: send a request through MEAI's chat client. The fake transport will throw on
        // response parsing, but we only care about the outbound headers, which are captured
        // before the response is parsed.
        try
        {
            await chatClient.GetResponseAsync("hi", cancellationToken: CancellationToken.None);
        }
        catch
        {
            // Expected: the fake response body is not parseable as a Responses API payload.
        }

        // Assert: at least one outbound request reached the transport, and its User-Agent
        // contains either "MEAI/" (auto-stamped by MEAI) or no MEAI segment (verification
        // signal — see test summary).
        Assert.True(handler.Count > 0, "Expected at least one outbound request from MEAI wrapper.");
        Assert.NotNull(handler.LastUserAgent);
        // INTENT: assert that MEAI auto-stamps. If the assertion fails, see the FoundryChatClient
        // implementation note about needing to register the MEAI policy explicitly.
        Assert.Contains("MEAI/", handler.LastUserAgent);
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
